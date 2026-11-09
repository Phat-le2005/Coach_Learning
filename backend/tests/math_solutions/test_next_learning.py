"""Post-assessment advice uses saved evidence; never calls AI or mutates mastery."""
# ruff: noqa: F401, F811 -- imported pytest fixtures

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.assignments.models import AssignmentDeliveryMode, StudentAssignmentStatus
from app.concepts.models import Concept
from app.curriculum.models import Chapter, Topic, ProblemType, LearningOutcome
from app.learning_evidence.models import (
    LearningEvidenceEvent,
    LearningEvidenceSourceKind,
)
from app.learning_evidence.skill_outcomes import KEY
from app.mastery.models import StudentConceptMastery
from app.math_solutions.models import (
    EvaluationDecision,
    SolutionAttempt,
    SolutionRubric,
)
from app.math_solutions.next_learning import (
    LaunchNextLearning,
    NextLearningService,
    criterion_gaps,
)
from app.practice.models import EvaluationStatus, PracticeSession
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionLearningOutcome,
    QuestionType,
    QuestionStatus,
)
from app.review.models import ReviewSchedule
from tests.math_solutions.test_v2_api import v2_domain, auth_headers, create_payload
from app.math_solutions.service import MathSolutionService
from app.core.exceptions import ApplicationError


@pytest.fixture
def case(db_session, v2_domain):
    s, d = db_session, v2_domain
    chapter = Chapter(
        subject_id=d.subject.id, code="CALC", name="Ứng dụng đạo hàm", order_index=0
    )
    concept = Concept(
        subject_id=d.subject.id,
        code="DERIVATIVE",
        name="Dấu của đạo hàm",
        grade_level=12,
        order_index=0,
    )
    outcome = LearningOutcome(
        subject_id=d.subject.id,
        code="LO_DERIVATIVE",
        description="Xét dấu đạo hàm",
        grade_level=12,
        order_index=0,
    )
    s.add_all([chapter, concept, outcome])
    s.flush()
    topic = Topic(chapter_id=chapter.id, code="MONO", name="Đơn điệu", order_index=0)
    s.add(topic)
    s.flush()
    pt = ProblemType(
        topic_id=topic.id, code="MONO_PT", name="Xét tính đơn điệu", order_index=0
    )
    s.add(pt)
    s.flush()

    def links(q):
        q.concept_links = [QuestionConcept(concept_id=concept.id, weight=1)]
        q.problem_type_links = [
            QuestionProblemType(problem_type_id=pt.id, weight=1, is_primary=True)
        ]
        q.learning_outcome_links = [
            QuestionLearningOutcome(learning_outcome_id=outcome.id, weight=1)
        ]

    links(d.question)
    next_q = Question(
        subject_id=d.subject.id,
        content="Xét tính đơn điệu của $y=x^3-6x$.",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.4,
        correct_answer="PRIVATE_ANSWER",
        explanation="PRIVATE_SOLUTION",
        source_type="TEST",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        created_by=d.teacher.id,
    )
    links(next_q)
    s.add(next_q)
    s.commit()
    payload = {
        **create_payload(d),
        "question_id": d.question.id,
        "practice_session_id": d.practice.id,
    }
    rubric = SolutionRubric(
        question_id=d.question.id,
        title="Rubric kiểm thử",
        status="APPROVED",
        criteria={
            "criteria": [
                {"id": "calculation", "title": "Tính đạo hàm", "weight": 0.5},
                {"id": "sign", "title": "Hoàn thiện bảng xét dấu", "weight": 0.5},
            ]
        },
    )
    s.add(rubric)
    s.commit()
    created = MathSolutionService(s).create(
        d.student.id, **payload, rubric_id=rubric.id
    )
    attempt = s.get(SolutionAttempt, UUID(created["id"]))
    attempt.status = "EVALUATED"
    decision = EvaluationDecision(
        id=uuid4(),
        attempt_id=attempt.id,
        rubric_id=rubric.id,
        decision_source="AUTOMATED_CONSENSUS",
        final_score=0.5,
        is_correct=False,
    )
    s.add(decision)
    s.flush()
    event = LearningEvidenceEvent(
        student_id=d.student_profile.id,
        subject_id=d.subject.id,
        source_kind=LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION,
        source_entity_id=decision.id,
        score=0.5,
        is_correct=False,
        evaluation_status=EvaluationStatus.EVALUATED,
        occurred_at=datetime.now(timezone.utc),
        event_metadata={
            KEY: {
                "version": 1,
                "concepts": {str(concept.id): {"score": 0.3, "is_correct": False}},
                "criteria": [
                    {
                        "criterion_id": "sign",
                        "weight": 0.5,
                        "achieved": 0,
                        "step_index": None,
                    }
                ],
            }
        },
    )
    s.add(event)
    s.flush()
    decision.learning_evidence_event_id = event.id
    s.add_all(
        [
            StudentConceptMastery(
                student_id=d.student_profile.id,
                concept_id=concept.id,
                mastery_score=0.35,
                confidence=0.5,
                attempt_count=3,
                correct_count=1,
                last_practiced_at=datetime.now(timezone.utc),
            ),
            ReviewSchedule(
                student_id=d.student_profile.id,
                concept_id=concept.id,
                next_review_at=datetime.now(timezone.utc) + timedelta(days=2),
                review_interval_days=2,
            ),
        ]
    )
    s.commit()
    return SimpleNamespace(
        d=d,
        s=s,
        attempt=attempt,
        decision=decision,
        concept=concept,
        next_q=next_q,
        rubric=rubric,
    )


def test_partial_score_recommends_explicit_target_and_exact_question_without_side_effects(
    case,
):
    c = case
    before = c.s.scalar(select(func.count()).select_from(SolutionAttempt))
    service = NextLearningService(c.s)
    result = service.get(c.d.student.id, c.attempt.id)
    again = service.get(c.d.student.id, c.attempt.id)
    assert result == again and result.status == "REINFORCE" and result.score == 0.5
    assert result.evidence_recorded and result.target.id == c.concept.id
    assert result.target.mastery_score == 0.35 and result.target.evidence_count == 3
    assert result.target.next_review_at is not None
    assert result.criterion_gaps[0].title == "Hoàn thiện bảng xét dấu"
    assert result.question.id == c.next_q.id
    assert (
        "PRIVATE_ANSWER" not in result.model_dump_json()
        and "PRIVATE_SOLUTION" not in result.model_dump_json()
    )
    assert not c.s.new and not c.s.dirty
    assert c.s.scalar(select(func.count()).select_from(SolutionAttempt)) == before


def test_launch_opens_exact_recommendation_and_replays_without_duplicate_session(case):
    c = case
    service = NextLearningService(c.s)
    request = LaunchNextLearning(decision_id=c.decision.id, question_id=c.next_q.id)
    before = c.s.scalar(select(func.count()).select_from(PracticeSession))
    target = service.launch(c.d.student.id, c.attempt.id, request)
    assert service.launch(c.d.student.id, c.attempt.id, request) == target
    attempt = c.s.get(SolutionAttempt, target)
    assert attempt.question_id == c.next_q.id and attempt.status == "DRAFT"
    assert c.s.scalar(select(func.count()).select_from(PracticeSession)) == before + 1
    assert (
        c.s.get(
            StudentConceptMastery, (c.d.student_profile.id, c.concept.id)
        ).attempt_count
        == 3
    )


@pytest.mark.parametrize("change", ["missing_reference", "archived", "already_seen"])
def test_no_valid_supply_does_not_fall_back_to_unrelated_question(case, change):
    c = case
    if change == "missing_reference":
        c.next_q.correct_answer = c.next_q.explanation = None
    elif change == "archived":
        c.next_q.status = QuestionStatus.ARCHIVED
    else:
        c.s.add(
            SolutionAttempt(
                student_id=c.d.student_profile.id,
                question_id=c.next_q.id,
                practice_session_id=c.d.practice.id,
                source_kind="CANONICAL",
                context_type="SELF_PRACTICE",
                mode="INDEPENDENT_SOLUTION",
                create_idempotency_key="already-seen",
            )
        )
    c.s.commit()
    result = NextLearningService(c.s).get(c.d.student.id, c.attempt.id)
    assert (
        result.question is None
        and result.target.id == c.concept.id
        and result.supply_message
    )


def test_without_final_decision_no_score_or_personalized_launch(case):
    c = case
    c.s.delete(c.decision)
    c.s.commit()
    result = NextLearningService(c.s).get(c.d.student.id, c.attempt.id)
    assert (
        result.status == "WAITING_REVIEW"
        and result.score is None
        and result.question is None
    )


def test_wrong_student_cannot_read_or_launch_and_stale_choice_is_rejected(case):
    c = case
    service = NextLearningService(c.s)
    with pytest.raises(ApplicationError) as e:
        service.get(c.d.outsider.id, c.attempt.id)
    assert e.value.status_code == 404
    with pytest.raises(ApplicationError):
        service.launch(
            c.d.outsider.id,
            c.attempt.id,
            LaunchNextLearning(decision_id=c.decision.id, question_id=c.next_q.id),
        )
    with pytest.raises(ApplicationError) as e:
        service.launch(
            c.d.student.id,
            c.attempt.id,
            LaunchNextLearning(decision_id=c.decision.id, question_id=uuid4()),
        )
    assert e.value.code == "LEARNING_SUGGESTION_CHANGED"


def test_high_score_is_not_a_mastery_claim_and_stale_criterion_evidence_not_used(case):
    c = case
    c.decision.final_score = 1
    c.decision.is_correct = True
    c.s.commit()
    result = NextLearningService(c.s).get(c.d.student.id, c.attempt.id)
    assert (
        result.status == "CONTINUE"
        and result.score == 1
        and not result.evidence_recorded
    )
    assert result.criterion_gaps == [] and result.target.mastery_score == 0.35


def test_api_requires_owner_and_role(db_client, case, auth_headers):
    c = case
    url = f"/api/v3/math-solutions/attempts/{c.attempt.id}/next-learning"
    assert db_client.get(url).status_code == 401
    assert db_client.get(url, headers=auth_headers(c.d.teacher)).status_code == 403
    assert db_client.get(url, headers=auth_headers(c.d.outsider)).status_code == 404
    result = db_client.get(url, headers=auth_headers(c.d.student))
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["question"]["id"] == str(c.next_q.id)


def test_active_exam_withholds_recommendations_before_whole_submission(monkeypatch):
    service = NextLearningService(
        SimpleNamespace(
            get=lambda *_: SimpleNamespace(status=StudentAssignmentStatus.IN_PROGRESS)
        )
    )
    monkeypatch.setattr(
        service,
        "_context",
        lambda *_: (
            SimpleNamespace(student_assignment_id=uuid4()),
            SimpleNamespace(delivery_mode=AssignmentDeliveryMode.EXAM),
            uuid4(),
        ),
    )
    result = service.get(uuid4(), uuid4())
    assert (
        result.status == "WAITING_SUBMISSION"
        and result.score is None
        and result.target is None
    )


def test_bad_or_missing_criterion_data_does_not_invent_deficits():
    assert criterion_gaps({}, None) == []
    assert (
        criterion_gaps(
            {KEY: {"criteria": [{"achieved": float("nan"), "weight": 1}, None]}}, None
        )
        == []
    )


def test_no_curriculum_mapping_returns_clear_supply_gap(case):
    c = case
    c.d.question.concept_links = []
    c.d.question.problem_type_links = []
    c.s.commit()
    result = NextLearningService(c.s).get(c.d.student.id, c.attempt.id)
    assert result.target is None and result.question is None
    assert "chưa được gắn" in result.supply_message


@pytest.mark.parametrize("mode", ["success", "unavailable", "not-configured"])
def test_optional_coach_explains_only_saved_facts_and_falls_back(monkeypatch, mode):
    import asyncio
    from app.math_solutions.next_learning_router import explain_next_learning, CoachText
    from app.math_solutions.next_learning import NextLearningRead, LearningTarget

    advice = NextLearningRead(
        attempt_id=uuid4(),
        decision_id=uuid4(),
        status="REINFORCE",
        score=0.5,
        headline="Củng cố",
        explanation="Ôn lại",
        target=LearningTarget(
            id=uuid4(),
            kind="CONCEPT",
            name="Dấu đạo hàm",
            reason="Tiêu chí chưa đạt đủ điểm.",
        ),
    )
    monkeypatch.setattr(NextLearningService, "get", lambda *args: advice)
    calls = []

    class Gateway:
        async def generate_structured(self, *args, **kwargs):
            calls.append((args, kwargs))
            assert kwargs["timeout"] == 8 and kwargs["max_retries"] == 0
            if mode == "unavailable":
                raise RuntimeError("Synthetic outage")
            return SimpleNamespace(
                data=CoachText(text="Ôn mối liên hệ dấu đạo hàm và chiều biến thiên.")
            )

    result = asyncio.run(
        explain_next_learning(
            advice.attempt_id,
            SimpleNamespace(id=uuid4()),
            None,
            None if mode == "not-configured" else Gateway(),
        )
    )
    assert result.source == ("AI_COACH" if mode == "success" else "LEARNING_CORE")
    if mode != "success":
        assert result.text == advice.target.reason
    assert len(calls) == (0 if mode == "not-configured" else 1)
