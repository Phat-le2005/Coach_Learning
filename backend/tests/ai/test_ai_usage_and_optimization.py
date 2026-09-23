import asyncio
import time
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.ai.context_trimmer import ContextTrimmer
from app.ai.exceptions import AIRateLimitError
from app.ai.rate_limiter import AIRateLimiter
from app.ai.routing_policy import ModelRoutingPolicy
from app.ai.schemas import AIUsageSummaryRead
from app.ai.tutor_context_builder import TutorContextBuilder
from app.ai.tutor_schemas import TutorContextData, TutorRequest
from app.ai.types import AIRoutingTier, AITaskType
from app.ai.usage_service import AIUsageService
from app.core.config import Settings
from app.mastery.strategy import (
    AttemptEvidence,
    DeterministicMasteryCalculationStrategy,
    MappingEvidence,
    MasteryState,
    QuestionEvidence,
)
from app.practice.evaluation import AnswerEvaluationService
from app.questions.models import Question, QuestionType
from app.users.models import Role, User


@pytest.fixture
def custom_settings() -> Settings:
    return Settings(
        database_name="test_edums",
        database_user="postgres",
        ai_provider="mock",
        ai_model_fast="gemini-2.5-flash-tuned",
        ai_model_standard="gemini-2.5-standard-tuned",
        ai_model_reasoning="gemini-2.5-pro-tuned",
        ai_embedding_model="text-embedding-004-tuned",
        ai_timeout_seconds=2.0,
        ai_max_retries=2,
        ai_rate_limit_per_minute=5,
        ai_daily_requests_limit_per_student=10,
        ai_rag_top_k=3,
        ai_max_context_chars=1500,
    )


# ==============================================================================
# 1. MODEL ROUTING POLICY & ENVIRONMENT-BASED MODEL NAMES
# ==============================================================================

def test_model_routing_policy_tiers(custom_settings: Settings):
    """Verify FAST, STANDARD, REASONING tiers and task resolution."""
    policy = ModelRoutingPolicy(custom_settings)

    assert policy.resolve_tier(AITaskType.TUTOR) == AIRoutingTier.FAST
    assert policy.resolve_tier(AITaskType.HINT) == AIRoutingTier.FAST
    assert policy.resolve_tier(AITaskType.RAG) == AIRoutingTier.FAST

    assert policy.resolve_tier(AITaskType.OPEN_RESPONSE_EVALUATION) == AIRoutingTier.STANDARD
    assert policy.resolve_tier(AITaskType.TEACHER_COPILOT) == AIRoutingTier.STANDARD
    assert policy.resolve_tier(AITaskType.ADMISSION_ASSISTANT) == AIRoutingTier.STANDARD

    assert policy.resolve_tier(AITaskType.EXAM_ANALYSIS) == AIRoutingTier.REASONING

    # Override takes precedence
    assert (
        policy.resolve_tier(AITaskType.TUTOR, override=AIRoutingTier.REASONING)
        == AIRoutingTier.REASONING
    )


def test_model_names_environment_based(custom_settings: Settings):
    """Verify model identifiers dynamically resolve from environment settings."""
    policy = ModelRoutingPolicy(custom_settings)

    assert policy.resolve_model(AIRoutingTier.FAST) == "gemini-2.5-flash-tuned"
    assert policy.resolve_model(AIRoutingTier.STANDARD) == "gemini-2.5-standard-tuned"
    assert policy.resolve_model(AIRoutingTier.REASONING) == "gemini-2.5-pro-tuned"
    assert policy.resolve_embedding_model() == "text-embedding-004-tuned"

    assert policy.resolve_model_for_task(AITaskType.TUTOR) == "gemini-2.5-flash-tuned"
    assert policy.resolve_model_for_task(AITaskType.EXAM_ANALYSIS) == "gemini-2.5-pro-tuned"


# ==============================================================================
# 2. CONTEXT TRIMMING & TOKEN BUDGETING
# ==============================================================================

def test_context_trimmer_bounds():
    """Verify context trimmer limits text length and respects word boundaries."""
    long_text = "Từ thuở xưa toán học đã đóng vai trò quan trọng trong việc mô tả thế giới tự nhiên và các quy luật vật lý sâu sắc."
    trimmed = ContextTrimmer.trim_text(long_text, max_chars=40)
    assert len(trimmed) <= 40
    assert trimmed.endswith("...")

    # Short text remains untouched
    short_text = "Toán giải tích 12"
    assert ContextTrimmer.trim_text(short_text, max_chars=50) == short_text

    # Session summary trimming
    long_summary = "Phiên học hôm nay tập trung vào khảo sát hàm số. " * 30
    trimmed_summary = ContextTrimmer.trim_session_summary(long_summary, max_chars=100)
    assert len(trimmed_summary) <= 100
    assert trimmed_summary.endswith("...")

    # Array item trimming
    items = list(range(10))
    assert ContextTrimmer.trim_items(items, max_items=4) == [0, 1, 2, 3]


def test_rag_top_k_limits():
    """Verify RAG chunks are strictly capped at top-k and per-chunk character limits."""
    chunks = [f"Tài liệu tham khảo số {i} với nội dung chi tiết về đạo hàm và ứng dụng." for i in range(10)]
    trimmed_chunks = ContextTrimmer.trim_rag_chunks(chunks, top_k=3, max_chars_per_chunk=35)

    assert len(trimmed_chunks) == 3
    for chunk in trimmed_chunks:
        assert len(chunk) <= 35
        assert chunk.endswith("...")


# ==============================================================================
# 3. STRICT TUTOR INPUT BOUNDARIES (NEVER FULL TWIN / GRAPH / CHAT / DOCS)
# ==============================================================================

def test_tutor_input_boundaries_strict(db_session):
    """Verify TutorContextBuilder output contains ONLY the 7 required fields:
    
    1. current request
    2. current ProblemType
    3. relevant Concepts/prerequisites
    4. compact mastery
    5. recent summary
    6. relevant memory
    7. RAG chunks
    
    And NEVER full digital twin, full mastery graph, full chat, or full docs.
    """
    user = User(
        id=uuid4(),
        email="test_tutor_student@edums.vn",
        password_hash="hashed_pw_test",
        full_name="Nguyễn Văn A",
        role=Role.STUDENT,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    builder = TutorContextBuilder(db_session)
    request = TutorRequest(
        message="Thầy ơi cho em hỏi cách tìm tiệm cận đứng của đồ thị hàm số phân thức bậc nhất.",
        session_summary="Đã thảo luận về tập xác định và giới hạn một bên của hàm số.",
    )

    context: TutorContextData = asyncio.run(builder.build_context(user, request))

    # 1. Current request exists and is bounded
    assert context.student_query.startswith("Thầy ơi cho em hỏi")
    assert len(context.student_query) <= 1000

    # 2. Current ProblemType exists (or clean fallback)
    assert context.problem_type_name is not None

    # 3. Relevant Concepts / prerequisites exists
    assert context.concept_context is not None

    # 4. Compact mastery exists (NOT full mastery graph)
    assert context.mastery_context is not None
    assert "StudentConceptMastery" not in context.mastery_context  # Raw DB models never dumped

    # 5. Recent summary exists (NOT full raw chat)
    assert "Đã thảo luận về tập xác định" in context.session_summary
    assert len(context.session_summary) <= 500

    # 6. Relevant memory exists (filtered, not dumped)
    assert context.learning_memory_context is not None

    # 7. RAG chunks exist as DATA
    assert context.rag_context is not None

    # Verify absence of forbidden full objects
    context_dict = context.model_dump()
    forbidden_keys = {"digital_twin", "full_chat_history", "mastery_graph", "all_documents"}
    for key in forbidden_keys:
        assert key not in context_dict, f"Forbidden key '{key}' found in TutorContextData!"


# ==============================================================================
# 4. AI ENDPOINTS RATE LIMITER & LEARNING CORE IMMUNITY
# ==============================================================================

def test_ai_rate_limiter_minute_window():
    """Verify that exceeding requests per minute triggers AIRateLimitError (429)."""
    limiter = AIRateLimiter(default_minute_limit=3, default_daily_limit=10)
    user_id = uuid4()

    # 3 allowed requests
    limiter.check_rate_limit(user_id)
    limiter.check_rate_limit(user_id)
    limiter.check_rate_limit(user_id)

    # 4th request exceeds minute limit
    with pytest.raises(AIRateLimitError) as exc_info:
        limiter.check_rate_limit(user_id)

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "AI_RATE_LIMIT_EXCEEDED"
    assert "minute" in exc_info.value.message
    assert exc_info.value.headers == {"Retry-After": "60"}


def test_ai_rate_limiter_daily_window():
    """Verify that exceeding requests per day triggers AIRateLimitError (429)."""
    limiter = AIRateLimiter(default_minute_limit=100, default_daily_limit=4)
    user_id = uuid4()

    for _ in range(4):
        limiter.check_rate_limit(user_id)

    # 5th request exceeds daily quota
    with pytest.raises(AIRateLimitError) as exc_info:
        limiter.check_rate_limit(user_id)

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "AI_RATE_LIMIT_EXCEEDED"
    assert "daily" in exc_info.value.message
    assert exc_info.value.headers == {"Retry-After": "86400"}


def test_learning_core_not_blocked_by_ai_quota():
    """Verify that exhausting AI rate limit quota NEVER blocks Learning Core operations.
    
    A student with zero AI quota can still:
    1. Evaluate objective answers in practice.
    2. Compute deterministic mastery progression.
    """
    limiter = AIRateLimiter(default_minute_limit=1, default_daily_limit=1)
    student_id = uuid4()

    # Exhaust AI quota
    limiter.check_rate_limit(student_id)
    with pytest.raises(AIRateLimitError):
        limiter.check_rate_limit(student_id)

    # Learning Core operations proceed with 100% success!
    eval_service = AnswerEvaluationService()
    question = Question(
        question_type=QuestionType.SHORT_ANSWER,
        correct_answer="π/2",
    )
    res = eval_service.evaluate(question, "π/2")
    assert res.is_correct is True
    assert res.score == 1.0

    calc_strategy = DeterministicMasteryCalculationStrategy()
    state = calc_strategy.calculate_from_attempt(
        previous_state=MasteryState(mastery_score=0.4, confidence=0.4, attempt_count=2, correct_count=1),
        question=QuestionEvidence(difficulty=0.5),
        mapping=MappingEvidence(weight=1.0),
        attempt=AttemptEvidence(is_correct=True, score=1.0, hint_count=0),
    )
    assert state.mastery_score > 0.4
    assert state.attempt_count == 3


# ==============================================================================
# 5. GRANULAR OBSERVABILITY METRICS
# ==============================================================================

def test_granular_usage_metrics(db_session):
    """Verify computation of:
    - average latency/task
    - tokens/task (total & avg)
    - requests/student/day
    - estimated cost/task (total & avg)
    """
    usage_svc = AIUsageService(db_session)
    user_a = User(
        id=uuid4(),
        email="student_a@edums.vn",
        password_hash="hash_a",
        full_name="Học sinh A",
        role=Role.STUDENT,
        is_active=True,
    )
    user_b = User(
        id=uuid4(),
        email="student_b@edums.vn",
        password_hash="hash_b",
        full_name="Học sinh B",
        role=Role.STUDENT,
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    db_session.flush()

    student_a = user_a.id
    student_b = user_b.id

    # Log 3 requests for TUTOR
    usage_svc.record_log(
        task=AITaskType.TUTOR,
        provider="mock",
        model="gemini-2.5-flash",
        latency_ms=100.0,
        input_tokens=150,
        output_tokens=50,
        success=True,
        user_id=student_a,
    )
    usage_svc.record_log(
        task=AITaskType.TUTOR,
        provider="mock",
        model="gemini-2.5-flash",
        latency_ms=200.0,
        input_tokens=250,
        output_tokens=150,
        success=True,
        user_id=student_b,
    )
    # Log 1 request for EXAM_ANALYSIS
    usage_svc.record_log(
        task=AITaskType.EXAM_ANALYSIS,
        provider="mock",
        model="gemini-2.5-pro",
        latency_ms=600.0,
        input_tokens=500,
        output_tokens=300,
        success=True,
        user_id=student_a,
    )

    summary: AIUsageSummaryRead = usage_svc.get_usage_summary()

    # 1. Global totals
    assert summary.total_requests == 3
    assert summary.successful_requests == 3
    assert summary.total_tokens == (200 + 400 + 800)

    # 2. Per-task metrics (average latency/task, tokens/task, estimated cost/task)
    metrics_by_task = usage_svc.get_metrics_per_task()
    assert "TUTOR" in metrics_by_task
    assert "EXAM_ANALYSIS" in metrics_by_task

    tutor_metrics = metrics_by_task["TUTOR"]
    assert tutor_metrics["requests"] == 2
    assert tutor_metrics["average_latency_ms"] == 150.0  # (100 + 200) / 2
    assert tutor_metrics["total_tokens"] == 600  # 200 + 400
    assert tutor_metrics["average_tokens_per_task"] == 300.0  # 600 / 2
    assert tutor_metrics["average_cost_per_task"] >= 0.0

    exam_metrics = metrics_by_task["EXAM_ANALYSIS"]
    assert exam_metrics["requests"] == 1
    assert exam_metrics["average_latency_ms"] == 600.0
    assert exam_metrics["total_tokens"] == 800

    # 3. Requests per student per day
    assert summary.average_requests_per_student_per_day > 0.0
    assert len(summary.student_daily_usage) >= 1
    daily_entry = summary.student_daily_usage[0]
    assert daily_entry.unique_students == 2  # student_a and student_b
    assert daily_entry.total_requests == 3
    assert daily_entry.average_requests_per_student == 1.5  # 3 requests / 2 students
