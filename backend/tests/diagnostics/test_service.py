from sqlalchemy import select
from sqlalchemy.orm import Session

from app.curriculum.models import Chapter, ProblemType, Topic
from app.diagnostics.models import (
    DiagnosticCompletionReason,
    DiagnosticSelectionReason,
)
from app.diagnostics.schemas import DiagnosticAnswerCreate, DiagnosticStartCreate
from app.diagnostics.service import DiagnosticService
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.models import PracticeSessionStatus
from app.students.models import StudentProfile
from app.users.models import User
from tests.diagnostics.conftest import DiagnosticContent


def _start(
    service: DiagnosticService,
    user: User,
    content: DiagnosticContent,
    *,
    max_questions: int = 6,
    coverage: float = 1.0,
    confidence: float = 1.0,
):
    return service.start(
        user,
        DiagnosticStartCreate(
            subject_id=content.base.subject.id,
            max_questions=max_questions,
            minimum_problem_type_coverage=coverage,
            confidence_threshold=confidence,
        ),
    )


def _answer(
    service: DiagnosticService,
    user: User,
    diagnostic_id,
    question_id,
    *,
    correct: bool,
):
    return service.answer(
        user,
        diagnostic_id,
        DiagnosticAnswerCreate(
            question_id=question_id,
            student_answer="TRUE" if correct else "FALSE",
            response_time_seconds=30.0,
            hint_count=0,
        ),
    )


def test_adaptive_difficulty_increases_after_correct_medium_answer(
    db_session: Session,
    practice_students: tuple[User, User],
    diagnostic_content: DiagnosticContent,
) -> None:
    service = DiagnosticService(db_session)
    started = _start(service, practice_students[0], diagnostic_content)

    first = service.next_question(practice_students[0], started.id)
    assert first.question is not None
    assert first.question.difficulty == 0.55
    assert first.desired_difficulty == 0.55
    _answer(service, practice_students[0], started.id, first.question.id, correct=True)

    second = service.next_question(practice_students[0], started.id)
    assert second.question is not None
    assert second.desired_difficulty == 0.75
    assert second.question.difficulty == 0.85


def test_blueprint_balances_chapter_topic_coverage(
    db_session: Session,
    practice_students: tuple[User, User],
    diagnostic_content: DiagnosticContent,
) -> None:
    started = _start(
        DiagnosticService(db_session), practice_students[0], diagnostic_content
    )
    rows = list(
        db_session.execute(
            select(ProblemType.id, Topic.id, Chapter.id)
            .join(Topic, Topic.id == ProblemType.topic_id)
            .join(Chapter, Chapter.id == Topic.chapter_id)
            .where(ProblemType.id.in_(started.blueprint_problem_type_ids))
        )
    )

    assert len(started.blueprint_problem_type_ids) == 3
    assert len({topic_id for _, topic_id, _ in rows}) == 3
    assert len({chapter_id for _, _, chapter_id in rows}) == 2


def test_confidence_and_coverage_stop_condition(
    db_session: Session,
    practice_students: tuple[User, User],
    diagnostic_content: DiagnosticContent,
) -> None:
    service = DiagnosticService(db_session)
    started = _start(
        service,
        practice_students[0],
        diagnostic_content,
        max_questions=6,
        coverage=0.5,
        confidence=0.1,
    )
    answer = None
    for _ in range(2):
        selected = service.next_question(practice_students[0], started.id)
        assert selected.question is not None
        answer = _answer(
            service,
            practice_students[0],
            started.id,
            selected.question.id,
            correct=True,
        )

    assert answer is not None
    assert answer.status == PracticeSessionStatus.COMPLETED
    assert answer.completion_reason == DiagnosticCompletionReason.CONFIDENCE_REACHED


def test_result_identifies_specific_weak_problem_type(
    db_session: Session,
    practice_students: tuple[User, User],
    diagnostic_content: DiagnosticContent,
) -> None:
    service = DiagnosticService(db_session)
    started = _start(
        service,
        practice_students[0],
        diagnostic_content,
        max_questions=2,
    )
    first = service.next_question(practice_students[0], started.id)
    assert first.question is not None
    _answer(service, practice_students[0], started.id, first.question.id, correct=True)
    second = service.next_question(practice_students[0], started.id)
    assert second.question is not None and second.target_problem_type_id is not None
    weak_id = second.target_problem_type_id
    _answer(service, practice_students[0], started.id, second.question.id, correct=False)

    result = service.result(practice_students[0], started.id)

    assert weak_id in result.weak_problem_types
    assert weak_id in result.recommended_starting_problem_types
    assert result.subject_summary.subject_id == diagnostic_content.base.subject.id
    assert len(result.chapter_summary) == 2
    assert len(result.topic_summary) == 3


def test_incorrect_answer_selects_direct_prerequisite_check(
    db_session: Session,
    practice_students: tuple[User, User],
    diagnostic_content: DiagnosticContent,
) -> None:
    service = DiagnosticService(db_session)
    started = _start(service, practice_students[0], diagnostic_content)
    first = service.next_question(practice_students[0], started.id)
    assert first.question is not None
    _answer(service, practice_students[0], started.id, first.question.id, correct=False)

    prerequisite = service.next_question(practice_students[0], started.id)

    assert prerequisite.question is not None
    assert prerequisite.question.id == diagnostic_content.prerequisite_question.id
    assert prerequisite.target_concept_id == diagnostic_content.prerequisite.id
    assert prerequisite.selection_reason == DiagnosticSelectionReason.PREREQUISITE_CHECK
    assert prerequisite.desired_difficulty == 0.35


def test_max_question_limit_completes_diagnostic(
    db_session: Session,
    practice_students: tuple[User, User],
    diagnostic_content: DiagnosticContent,
) -> None:
    service = DiagnosticService(db_session)
    started = _start(
        service,
        practice_students[0],
        diagnostic_content,
        max_questions=1,
    )
    selected = service.next_question(practice_students[0], started.id)
    assert selected.question is not None

    answer = _answer(
        service,
        practice_students[0],
        started.id,
        selected.question.id,
        correct=True,
    )

    assert answer.status == PracticeSessionStatus.COMPLETED
    assert answer.completion_reason == DiagnosticCompletionReason.MAX_QUESTIONS
    assert service.next_question(practice_students[0], started.id).question is None


def test_answer_publishes_problem_type_and_concept_mastery_evidence(
    db_session: Session,
    practice_students: tuple[User, User],
    student_profile: StudentProfile,
    diagnostic_content: DiagnosticContent,
) -> None:
    service = DiagnosticService(db_session)
    started = _start(
        service,
        practice_students[0],
        diagnostic_content,
        max_questions=1,
    )
    selected = service.next_question(practice_students[0], started.id)
    assert selected.question is not None and selected.target_problem_type_id is not None
    _answer(
        service,
        practice_students[0],
        started.id,
        selected.question.id,
        correct=True,
    )

    problem_mastery = db_session.get(
        StudentProblemTypeMastery,
        (student_profile.id, selected.target_problem_type_id),
    )
    concept_mastery = db_session.get(
        StudentConceptMastery,
        (student_profile.id, diagnostic_content.base.concept.id),
    )
    assert problem_mastery is not None and problem_mastery.attempt_count == 1
    assert concept_mastery is not None and concept_mastery.attempt_count == 1
