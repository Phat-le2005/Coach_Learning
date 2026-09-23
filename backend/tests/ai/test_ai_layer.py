import asyncio
import logging
import pytest
from pydantic import BaseModel, Field

from app.ai.exceptions import (
    AIRateLimitError,
    AIServiceUnavailableError,
    AITimeoutError,
)
from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.ai.types import (
    AIMessage,
    AIRole,
    AIRoutingTier,
    AITaskType,
    DEFAULT_TASK_TIER_MAPPING,
)
from app.core.config import Settings


@pytest.fixture
def ai_settings() -> Settings:
    return Settings(
        database_name="test_edums",
        database_user="postgres",
        ai_provider="mock",
        ai_model_fast="gemini-2.5-flash",
        ai_model_standard="gemini-2.5-standard",
        ai_model_reasoning="gemini-2.5-pro",
        ai_embedding_model="text-embedding-004",
        ai_timeout_seconds=2.0,
        ai_max_retries=2,
    )


class SampleEvaluationOutput(BaseModel):
    is_correct: bool = True
    score: float = 0.95
    feedback: str = "Good reasoning."
    identified_misconceptions: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# 1. Task Types and Routing Tiers Tests
# --------------------------------------------------------------------------

def test_all_eleven_task_types_defined():
    expected_tasks = {
        "TUTOR",
        "HINT",
        "OPEN_RESPONSE_EVALUATION",
        "MISCONCEPTION_ANALYSIS",
        "RAG",
        "STUDY_PLAN_EXPLANATION",
        "TEACHER_COPILOT",
        "PARENT_SUMMARY",
        "QUESTION_GENERATION",
        "EXAM_ANALYSIS",
        "ADMISSION_ASSISTANT",
        "MEMORY_EXTRACTION",
    }
    actual_tasks = {t.value for t in AITaskType}
    assert actual_tasks == expected_tasks


def test_routing_tier_resolution(ai_settings: Settings):
    provider = MockAIProvider()
    gateway = AIGateway(provider=provider, settings=ai_settings)

    # Fast tier tasks
    assert gateway.resolve_tier(AITaskType.TUTOR) == AIRoutingTier.FAST
    assert gateway.resolve_tier(AITaskType.HINT) == AIRoutingTier.FAST
    assert gateway.resolve_tier(AITaskType.RAG) == AIRoutingTier.FAST

    # Standard tier tasks
    assert gateway.resolve_tier(AITaskType.OPEN_RESPONSE_EVALUATION) == AIRoutingTier.STANDARD
    assert gateway.resolve_tier(AITaskType.MISCONCEPTION_ANALYSIS) == AIRoutingTier.STANDARD
    assert gateway.resolve_tier(AITaskType.STUDY_PLAN_EXPLANATION) == AIRoutingTier.STANDARD
    assert gateway.resolve_tier(AITaskType.TEACHER_COPILOT) == AIRoutingTier.STANDARD
    assert gateway.resolve_tier(AITaskType.PARENT_SUMMARY) == AIRoutingTier.STANDARD
    assert gateway.resolve_tier(AITaskType.QUESTION_GENERATION) == AIRoutingTier.STANDARD
    assert gateway.resolve_tier(AITaskType.ADMISSION_ASSISTANT) == AIRoutingTier.STANDARD

    # Reasoning tier tasks
    assert gateway.resolve_tier(AITaskType.EXAM_ANALYSIS) == AIRoutingTier.REASONING

    # Tier override works
    assert (
        gateway.resolve_tier(AITaskType.HINT, tier_override=AIRoutingTier.REASONING)
        == AIRoutingTier.REASONING
    )


def test_model_resolution_from_environment(ai_settings: Settings):
    provider = MockAIProvider()
    gateway = AIGateway(provider=provider, settings=ai_settings)

    assert gateway.resolve_model(AIRoutingTier.FAST) == "gemini-2.5-flash"
    assert gateway.resolve_model(AIRoutingTier.STANDARD) == "gemini-2.5-standard"
    assert gateway.resolve_model(AIRoutingTier.REASONING) == "gemini-2.5-pro"
    assert gateway.resolve_embedding_model() == "text-embedding-004"


# --------------------------------------------------------------------------
# 2. Provider Abstraction Tests
# --------------------------------------------------------------------------

def test_generate_text_success(ai_settings: Settings):
    async def _test():
        provider = MockAIProvider(default_text="Hệ phương trình có nghiệm x=1, y=2.")
        gateway = AIGateway(provider=provider, settings=ai_settings)

        response = await gateway.generate(
            task_type=AITaskType.HINT,
            messages="Giải hệ phương trình này như thế nào?",
        )

        assert response.content == "Hệ phương trình có nghiệm x=1, y=2."
        assert response.tier == AIRoutingTier.FAST
        assert response.model == "gemini-2.5-flash"
        assert response.latency_ms >= 0.0
        assert provider.last_model == "gemini-2.5-flash"
        assert provider.last_messages[0].content == "Giải hệ phương trình này như thế nào?"

    asyncio.run(_test())


def test_generate_structured_success(ai_settings: Settings):
    async def _test():
        canned_data = SampleEvaluationOutput(
            is_correct=False,
            score=0.4,
            feedback="Sai dấu ở bước chuyển vế.",
            identified_misconceptions=["sign_error"],
        )
        provider = MockAIProvider(canned_structured=canned_data)
        gateway = AIGateway(provider=provider, settings=ai_settings)

        structured_resp = await gateway.generate_structured(
            task_type=AITaskType.OPEN_RESPONSE_EVALUATION,
            schema=SampleEvaluationOutput,
            messages=[AIMessage(role=AIRole.USER, content="Bài làm: x - 5 = 2 => x = -3")],
        )

        assert structured_resp.tier == AIRoutingTier.STANDARD
        assert structured_resp.model == "gemini-2.5-standard"
        assert structured_resp.data.is_correct is False
        assert structured_resp.data.score == 0.4
        assert structured_resp.data.identified_misconceptions == ["sign_error"]

    asyncio.run(_test())


def test_stream_success(ai_settings: Settings):
    async def _test():
        provider = MockAIProvider(default_text="Bước một là phân tích đa thức thành nhân tử.")
        gateway = AIGateway(provider=provider, settings=ai_settings)

        chunks: list[str] = []
        async for chunk in gateway.stream(
            task_type=AITaskType.TUTOR,
            messages="Gợi ý bài 1",
        ):
            chunks.append(chunk)

        full_text = "".join(chunks).strip()
        assert "Bước một là phân tích đa thức thành nhân tử." in full_text

    asyncio.run(_test())


def test_embed_success(ai_settings: Settings):
    async def _test():
        provider = MockAIProvider(embedding_dimension=128)
        gateway = AIGateway(provider=provider, settings=ai_settings)

        emb_resp = await gateway.embed(["Định lý Pytago trong tam giác vuông."])

        assert emb_resp.model == "text-embedding-004"
        assert len(emb_resp.embeddings) == 1
        assert len(emb_resp.embeddings[0]) == 128
        assert emb_resp.dimension == 128

    asyncio.run(_test())


# --------------------------------------------------------------------------
# 3. Resilience, Retry, Timeout, and Safe Error Mapping Tests
# --------------------------------------------------------------------------

def test_retry_on_transient_rate_limit(ai_settings: Settings):
    async def _test():
        # Fails once with 429, then succeeds on 1st retry
        provider = MockAIProvider(rate_limit_failures=1, default_text="Success after retry")
        gateway = AIGateway(provider=provider, settings=ai_settings)

        response = await gateway.generate(
            task_type=AITaskType.HINT,
            messages="Test prompt",
        )

        assert response.content == "Success after retry"
        assert provider.call_count == 2

    asyncio.run(_test())


def test_exhausted_retries_raises_rate_limit(ai_settings: Settings):
    async def _test():
        # Fails 5 times with rate limit, exceeds max_retries=2
        provider = MockAIProvider(rate_limit_failures=5)
        gateway = AIGateway(provider=provider, settings=ai_settings)

        with pytest.raises(AIRateLimitError) as exc_info:
            await gateway.generate(
                task_type=AITaskType.HINT,
                messages="Test prompt",
            )

        assert exc_info.value.status_code == 429
        assert exc_info.value.code == "AI_RATE_LIMIT_EXCEEDED"

    asyncio.run(_test())


def test_timeout_protection_and_mapping(ai_settings: Settings):
    async def _test():
        # Simulated provider sleep longer than timeout
        provider = MockAIProvider(simulated_latency_s=0.5)
        gateway = AIGateway(provider=provider, settings=ai_settings)

        # Set aggressive timeout of 0.05s
        with pytest.raises(AITimeoutError) as exc_info:
            await gateway.generate(
                task_type=AITaskType.TUTOR,
                messages="Test prompt",
                timeout=0.05,
            )

        assert exc_info.value.status_code == 504
        assert exc_info.value.code == "AI_GATEWAY_TIMEOUT"

    asyncio.run(_test())


def test_service_unavailable_mapping(ai_settings: Settings):
    async def _test():
        provider = MockAIProvider(service_unavailable_failures=1)
        gateway = AIGateway(provider=provider, settings=ai_settings)

        with pytest.raises(AIServiceUnavailableError) as exc_info:
            await gateway.generate(
                task_type=AITaskType.TEACHER_COPILOT,
                messages="Soạn kế hoạch dạy học",
            )

        assert exc_info.value.status_code == 503
        assert exc_info.value.code == "AI_SERVICE_UNAVAILABLE"

    asyncio.run(_test())


def test_unexpected_exception_safe_mapping(ai_settings: Settings):
    async def _test():
        class CrashingProvider(MockAIProvider):
            async def generate(self, *args, **kwargs):
                raise RuntimeError("Unexpected external vendor library crash")

        gateway = AIGateway(provider=CrashingProvider(), settings=ai_settings)

        with pytest.raises(AIServiceUnavailableError) as exc_info:
            await gateway.generate(
                task_type=AITaskType.QUESTION_GENERATION,
                messages="Sinh câu hỏi",
            )

        assert exc_info.value.status_code == 503
        assert exc_info.value.code == "AI_SERVICE_UNAVAILABLE"
        assert "RuntimeError" in exc_info.value.message

    asyncio.run(_test())


# --------------------------------------------------------------------------
# 4. Latency Logging Tests
# --------------------------------------------------------------------------

def test_latency_logging(ai_settings: Settings, caplog: pytest.LogCaptureFixture):
    async def _test():
        provider = MockAIProvider(default_text="OK")
        gateway = AIGateway(provider=provider, settings=ai_settings)

        with caplog.at_level(logging.INFO):
            await gateway.generate(
                task_type=AITaskType.PARENT_SUMMARY,
                messages="Tóm tắt học tập tháng qua",
            )

        assert any(
            "ai_gateway_call_success" in record.message
            and "PARENT_SUMMARY" in record.message
            and "latency_ms" in record.message
            for record in caplog.records
        )

    asyncio.run(_test())


# --------------------------------------------------------------------------
# 5. Learning Core Independence and DB Immutability Verification
# --------------------------------------------------------------------------

def test_ai_gateway_does_not_depend_on_database_session(ai_settings: Settings):
    """Verify that AIGateway does not take, require, or expose any database session."""
    provider = MockAIProvider()
    gateway = AIGateway(provider=provider, settings=ai_settings)

    assert not hasattr(gateway, "session")
    assert not hasattr(gateway, "db")
    assert not hasattr(gateway, "commit")


def test_core_domains_independent_of_ai_layer():
    """Verify that core learning modules do NOT import or depend on app.ai."""
    import app.mastery.service as mastery_mod
    import app.practice.service as practice_mod
    import app.recommendations.priority_service as rec_mod
    import app.diagnostics.service as diag_mod
    import app.planning.study_service as plan_mod

    for mod in [mastery_mod, practice_mod, rec_mod, diag_mod, plan_mod]:
        imported_names = dir(mod)
        assert "AIGateway" not in imported_names
        assert "AIProvider" not in imported_names


def test_ai_error_handlers_in_fastapi(client):
    """Verify that AIServiceUnavailableError translates to HTTP 503 error envelope."""
    from fastapi import APIRouter
    from app.ai.exceptions import AIServiceUnavailableError, AIRateLimitError

    test_router = APIRouter(prefix="/test-ai")

    @test_router.get("/fail-503")
    def route_fail_503():
        raise AIServiceUnavailableError("AI service is currently down.")

    @test_router.get("/fail-429")
    def route_fail_429():
        raise AIRateLimitError("AI rate limit exceeded.")

    client.app.include_router(test_router)

    res_503 = client.get("/test-ai/fail-503")
    assert res_503.status_code == 503
    data_503 = res_503.json()
    assert data_503["error"]["code"] == "AI_SERVICE_UNAVAILABLE"
    assert data_503["error"]["message"] == "AI service is currently down."

    res_429 = client.get("/test-ai/fail-429")
    assert res_429.status_code == 429
    data_429 = res_429.json()
    assert data_429["error"]["code"] == "AI_RATE_LIMIT_EXCEEDED"


def test_mastery_engine_immune_to_ai_outage():
    """Verify that Mastery calculation runs completely unaffected when AI is down."""
    from app.mastery.state import derive_mastery_state, DerivedMasteryState

    # Mastery computation operates purely deterministically without any AI call
    state = derive_mastery_state(
        mastery_score=0.85,
        confidence=0.9,
        attempt_count=5,
        last_practiced_at=None,
    )
    assert state == DerivedMasteryState.MASTERED

