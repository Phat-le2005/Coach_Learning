import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.hints.models import HintLevel, HintSource, PracticeQuestionHint, QuestionHint
from app.hints.schemas import HintRequest
from app.hints.service import HintService
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.models import QuestionAttempt
from app.practice.schemas import PracticeAnswerCreate, PracticeSessionCreate
from app.practice.service import PracticeService
from app.students.models import StudentProfile
from app.users.models import User
from tests.practice.conftest import PracticeContent


def _gateway(
    settings: Settings,
    *,
    content: str = "Use the mapped concept and inspect the sign first.",
    concept_codes: list[str] | None = None,
    reveals_final_answer: bool = False,
) -> tuple[AIGateway, MockAIProvider]:
    provider = MockAIProvider(
        canned_structured={
            "content": content,
            "referenced_concept_codes": concept_codes or [],
            "reveals_final_answer": reveals_final_answer,
        }
    )
    return AIGateway(provider=provider, settings=settings), provider


def _practice_and_current_question(
    db_session: Session,
    student: User,
    content: PracticeContent,
):
    practice = PracticeService(db_session).create_session(
        student,
        PracticeSessionCreate(
            subject_id=content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=[content.problem_type.id],
            concept_ids=[content.concept.id],
        ),
    )
    question = PracticeService(db_session).get_next_question(student, practice.id)
    return practice, question


def _request(
    service: HintService,
    student: User,
    practice_id,
    question_id,
    level: HintLevel,
):
    return asyncio.run(
        service.get_hint(
            student,
            question_id,
            HintRequest(
                practice_session_id=practice_id,
                current_hint_level=level,
            ),
        )
    )


def test_predefined_hint_has_priority_and_does_not_update_learning_state(
    db_session: Session,
    settings: Settings,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    student, _ = practice_students
    practice, question = _practice_and_current_question(
        db_session, student, practice_content
    )
    db_session.add(
        QuestionHint(
            question_id=question.id,
            hint_level=HintLevel.LEVEL_1,
            content="Recall the mapped rule before choosing a method.",
        )
    )
    db_session.commit()
    gateway, provider = _gateway(settings)

    hint = _request(
        HintService(db_session, gateway=gateway),
        student,
        practice.id,
        question.id,
        HintLevel.LEVEL_1,
    )

    assert hint.hint_source == HintSource.PREDEFINED
    assert hint.hint_count == 1
    assert provider.call_count == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionAttempt)) == 0
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(StudentConceptMastery)
            .where(StudentConceptMastery.student_id == student_profile.id)
        )
        == 0
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(StudentProblemTypeMastery)
            .where(StudentProblemTypeMastery.student_id == student_profile.id)
        )
        == 0
    )


def test_ai_fallback_receives_only_mapped_curriculum_and_compact_mastery(
    db_session: Session,
    settings: Settings,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    practice, question = _practice_and_current_question(
        db_session, student, practice_content
    )
    gateway, provider = _gateway(
        settings, concept_codes=[practice_content.concept.code]
    )

    hint = _request(
        HintService(db_session, gateway=gateway),
        student,
        practice.id,
        question.id,
        HintLevel.LEVEL_1,
    )

    assert hint.hint_source == HintSource.AI
    assert provider.call_count == 1
    assert provider.last_messages is not None
    prompt = provider.last_messages[0].content
    assert practice_content.problem_type.code in prompt
    assert practice_content.concept.code in prompt
    assert practice_content.learning_outcome.code in prompt
    assert "NOT_STARTED" in prompt
    assert "LEVEL_1" in prompt


def test_hint_levels_are_sequential_and_same_level_retry_is_idempotent(
    db_session: Session,
    settings: Settings,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    practice, question = _practice_and_current_question(
        db_session, student, practice_content
    )
    gateway, provider = _gateway(settings)
    service = HintService(db_session, gateway=gateway)

    with pytest.raises(ApplicationError) as skipped:
        _request(
            service,
            student,
            practice.id,
            question.id,
            HintLevel.LEVEL_2,
        )
    assert skipped.value.code == "HINT_LEVEL_OUT_OF_SEQUENCE"

    first = _request(
        service, student, practice.id, question.id, HintLevel.LEVEL_1
    )
    retry = _request(
        service, student, practice.id, question.id, HintLevel.LEVEL_1
    )
    second = _request(
        service, student, practice.id, question.id, HintLevel.LEVEL_2
    )

    assert retry.id == first.id
    assert second.hint_count == 2
    assert provider.call_count == 2
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PracticeQuestionHint)
            .where(PracticeQuestionHint.practice_session_id == practice.id)
        )
        == 2
    )


def test_ai_cannot_invent_concept_or_reveal_answer_before_level_four(
    db_session: Session,
    settings: Settings,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    practice, question = _practice_and_current_question(
        db_session, student, practice_content
    )
    invented_gateway, _ = _gateway(settings, concept_codes=["UNMAPPED_CONCEPT"])
    with pytest.raises(ApplicationError) as invented:
        _request(
            HintService(db_session, gateway=invented_gateway),
            student,
            practice.id,
            question.id,
            HintLevel.LEVEL_1,
        )
    assert invented.value.code == "AI_HINT_CURRICULUM_VIOLATION"

    reveal_gateway, _ = _gateway(settings, reveals_final_answer=True)
    with pytest.raises(ApplicationError) as reveal:
        _request(
            HintService(db_session, gateway=reveal_gateway),
            student,
            practice.id,
            question.id,
            HintLevel.LEVEL_1,
        )
    assert reveal.value.code == "AI_HINT_POLICY_VIOLATION"


def test_other_student_cannot_request_hint(
    db_session: Session,
    settings: Settings,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    owner, outsider = practice_students
    practice, question = _practice_and_current_question(
        db_session, owner, practice_content
    )
    gateway, _ = _gateway(settings)

    with pytest.raises(ApplicationError) as denied:
        _request(
            HintService(db_session, gateway=gateway),
            outsider,
            practice.id,
            question.id,
            HintLevel.LEVEL_1,
        )
    assert denied.value.code == "PRACTICE_SESSION_ACCESS_DENIED"


def test_completed_attempt_uses_persisted_hint_count(
    db_session: Session,
    settings: Settings,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    practice, question = _practice_and_current_question(
        db_session, student, practice_content
    )
    db_session.add(
        QuestionHint(
            question_id=question.id,
            hint_level=HintLevel.LEVEL_1,
            content="Recall the relevant mapped concept.",
        )
    )
    db_session.commit()
    gateway, _ = _gateway(settings)
    _request(
        HintService(db_session, gateway=gateway),
        student,
        practice.id,
        question.id,
        HintLevel.LEVEL_1,
    )

    attempt = PracticeService(db_session).answer(
        student,
        practice.id,
        PracticeAnswerCreate(
            question_id=question.id,
            student_answer=question.correct_answer or "Reasoned response",
            hint_count=0,
        ),
    )

    assert attempt.hint_count == 1
