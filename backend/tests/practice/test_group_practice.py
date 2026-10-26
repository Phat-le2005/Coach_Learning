from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import (
    ProblemType,
    ProblemTypeConcept,
    ProblemTypeLearningOutcome,
)
from app.mastery.evidence import MasteryAttemptEvidencePublisher
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.evidence import AttemptEvaluatedEvidence
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    QuestionAttempt,
    QuestionGroupAttempt,
    QuestionGroupAttemptItem,
)
from app.practice.schemas import (
    PracticeAnswerCreate,
    PracticeGroupAnswerCreate,
    PracticeSessionCreate,
)
from app.practice.service import PracticeService
from app.questions.eligibility import standalone_question_only
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.questions.service import QuestionService
from app.review.models import ReviewSchedule
from app.users.models import Role, User
from tests.practice.conftest import PracticeContent
from tests.practice.group_helpers import create_group, create_other_subject


@dataclass
class RecordingPublisher:
    events: list[AttemptEvaluatedEvidence] = field(default_factory=list)

    def publish(self, evidence: AttemptEvaluatedEvidence, session: Session) -> None:
        self.events.append(evidence)


class FailOnThirdPublisher:
    def __init__(self) -> None:
        self.calls = 0
        self.delegate = MasteryAttemptEvidencePublisher()

    def publish(self, evidence: AttemptEvaluatedEvidence, session: Session) -> None:
        self.calls += 1
        if self.calls == 3:
            raise RuntimeError("third child evidence failed")
        self.delegate.publish(evidence, session)


def _teacher(factory, suffix: str) -> User:
    return factory(Role.TEACHER, f"group-{suffix}@example.com")


def _practice(
    service: PracticeService,
    student: User,
    content: PracticeContent,
    *,
    problem_type_ids: list[UUID] | None = None,
    concept_ids: list[UUID] | None = None,
) -> PracticeSession:
    return service.create_session(
        student,
        PracticeSessionCreate(
            subject_id=content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=(
                [content.problem_type.id]
                if problem_type_ids is None
                else problem_type_ids
            ),
            concept_ids=[content.concept.id] if concept_ids is None else concept_ids,
        ),
    )


def _answers(correct_count: int) -> PracticeGroupAnswerCreate:
    expected = {"a": "TRUE", "b": "FALSE", "c": "TRUE", "d": "FALSE"}
    values = []
    for index, label in enumerate("abcd"):
        answer = expected[label]
        if index >= correct_count:
            answer = "FALSE" if answer == "TRUE" else "TRUE"
        values.append({"label": label, "student_answer": answer})
    return PracticeGroupAnswerCreate(
        question_group_id=UUID(int=0),
        answers=values,
        response_time_seconds=120.5,
    )


def _group_answers(group_id: UUID, correct_count: int) -> PracticeGroupAnswerCreate:
    return _answers(correct_count).model_copy(update={"question_group_id": group_id})


def test_eligible_group_is_first_item_and_hides_answers(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    grouped = create_group(
        db_session, practice_content, _teacher(practice_user_factory, "read")
    )
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(service, student, practice_content)

    item = service.get_next_item(student, practice.id)
    payload = item.model_dump(mode="json")

    assert payload["item_type"] == "QUESTION_GROUP"
    assert payload["question"] is None
    assert payload["question_group"]["id"] == str(grouped.group.id)
    assert payload["question_group"]["scoring_policy"] == "MOET_2025_TRUE_FALSE"
    assert [row["label"] for row in payload["question_group"]["items"]] == list("abcd")
    assert [row["order_index"] for row in payload["question_group"]["items"]] == list(range(4))
    serialized = str(payload).casefold()
    assert "correct_answer" not in serialized
    assert "is_correct" not in serialized
    assert "answer_evidence" not in serialized


def test_group_missing_child_answer_is_not_offered(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    grouped = create_group(db_session, practice_content, _teacher(practice_user_factory, "no-key"))
    grouped.children[0].correct_answer = None
    db_session.commit()
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(service, student, practice_content)
    assert db_session.scalar(service._eligible_groups(practice, exclude_attempted=False)) is None


@pytest.mark.parametrize(
    "case",
    [
        "group-draft",
        "child-draft",
        "child-archived",
        "wrong-type",
        "no-problem-type",
        "no-concept",
        "no-outcome",
        "cross-subject-child",
        "malformed-order",
        "other-subject-group",
    ],
)
def test_ineligible_group_is_never_selected_or_accepted(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
    case: str,
) -> None:
    student, _ = practice_students
    author = _teacher(practice_user_factory, f"invalid-{case}")
    kwargs: dict[str, object] = {}
    if case == "group-draft":
        kwargs["group_status"] = QuestionStatus.DRAFT
    elif case == "child-draft":
        kwargs["child_status"] = QuestionStatus.DRAFT
    elif case == "child-archived":
        kwargs["child_status"] = QuestionStatus.ARCHIVED
    elif case == "wrong-type":
        kwargs["child_type"] = QuestionType.SHORT_ANSWER
    elif case.startswith("no-"):
        kwargs["missing_mapping"] = {
            "no-problem-type": "problem_type",
            "no-concept": "concept",
            "no-outcome": "learning_outcome",
        }[case]
    elif case == "malformed-order":
        kwargs["label_orders"] = (("a", 1), ("b", 0), ("c", 2), ("d", 3))
    elif case == "other-subject-group":
        kwargs["group_subject_id"] = create_other_subject(db_session).id
    grouped = create_group(db_session, practice_content, author, **kwargs)
    if case == "cross-subject-child":
        grouped.children[0].subject_id = create_other_subject(db_session).id
        db_session.commit()
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(service, student, practice_content)

    next_item = service.get_next_item(student, practice.id)
    assert next_item.item_type == "QUESTION"
    with pytest.raises(ApplicationError) as error:
        service.answer_group(
            student,
            practice.id,
            _group_answers(grouped.group.id, 4),
        )
    assert error.value.code == "QUESTION_GROUP_NOT_ELIGIBLE"
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupAttempt)) == 0


@pytest.mark.parametrize(
    "answers",
    [
        [
            {"label": "a", "student_answer": "TRUE"},
            {"label": "b", "student_answer": "FALSE"},
            {"label": "c", "student_answer": "TRUE"},
        ],
        [
            {"label": label, "student_answer": "TRUE"}
            for label in ("a", "b", "c", "d", "a")
        ],
        [
            {"label": label, "student_answer": "TRUE"}
            for label in ("a", "a", "c", "d")
        ],
        [
            {"label": label, "student_answer": "TRUE"}
            for label in ("a", "b", "c", "x")
        ],
        [
            {"label": "a", "student_answer": "YES"},
            {"label": "b", "student_answer": "FALSE"},
            {"label": "c", "student_answer": "TRUE"},
            {"label": "d", "student_answer": "FALSE"},
        ],
    ],
)
def test_group_answer_schema_requires_exact_normalized_shape(
    answers: list[dict[str, str]],
) -> None:
    with pytest.raises(ValidationError):
        PracticeGroupAnswerCreate(question_group_id=UUID(int=1), answers=answers)


def test_group_answer_schema_normalizes_existing_true_false_semantics() -> None:
    data = PracticeGroupAnswerCreate(
        question_group_id=UUID(int=1),
        answers=[
            {"label": " A ", "student_answer": "  TRUE "},
            {"label": "B", "student_answer": " false "},
            {"label": "c", "student_answer": "TrUe"},
            {"label": "d", "student_answer": "FaLsE"},
        ],
    )
    assert [(row.label, row.student_answer) for row in data.answers] == [
        ("a", "TRUE"),
        ("b", "FALSE"),
        ("c", "TRUE"),
        ("d", "FALSE"),
    ]


@pytest.mark.parametrize(
    ("correct_count", "expected_score"),
    [(0, 0.0), (1, 0.1), (2, 0.25), (3, 0.5), (4, 1.0)],
)
def test_real_group_submission_uses_moet_scoring_matrix(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
    correct_count: int,
    expected_score: float,
) -> None:
    student, _ = practice_students
    grouped = create_group(
        db_session,
        practice_content,
        _teacher(practice_user_factory, f"score-{correct_count}"),
    )
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(service, student, practice_content)

    attempt = service.answer_group(
        student,
        practice.id,
        _group_answers(grouped.group.id, correct_count),
    )

    assert attempt.correct_count == correct_count
    assert attempt.score == expected_score


def test_group_submission_persists_parent_children_links_and_four_events(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    grouped = create_group(
        db_session, practice_content, _teacher(practice_user_factory, "shape")
    )
    publisher = RecordingPublisher()
    service = PracticeService(db_session, evidence_publisher=publisher)
    practice = _practice(service, student, practice_content)

    parent = service.answer_group(
        student, practice.id, _group_answers(grouped.group.id, 3)
    )
    links = list(db_session.scalars(
        select(QuestionGroupAttemptItem)
        .where(QuestionGroupAttemptItem.question_group_attempt_id == parent.id)
        .order_by(QuestionGroupAttemptItem.order_index)
    ))
    attempts = [db_session.get(QuestionAttempt, link.question_attempt_id) for link in links]

    assert db_session.scalar(select(func.count()).select_from(QuestionGroupAttempt)) == 1
    assert db_session.scalar(select(func.count()).select_from(QuestionAttempt)) == 4
    assert len(links) == 4
    assert all(attempt is not None for attempt in attempts)
    assert [link.label for link in links] == list("abcd")
    assert [attempt.attempt_number for attempt in attempts if attempt] == [1, 2, 3, 4]
    assert all(
        attempt.evaluation_status == EvaluationStatus.AUTO_EVALUATED
        and attempt.score in {0.0, 1.0}
        and attempt.hint_count == 0
        and attempt.response_time_seconds is None
        for attempt in attempts
        if attempt
    )
    assert parent.response_time_seconds == 120.5
    assert parent.scoring_policy.value == "MOET_2025_TRUE_FALSE"
    assert len(publisher.events) == 4
    assert [event.question_id for event in publisher.events] == [
        child.id for child in grouped.children
    ]
    assert all(
        event.problem_type_ids == (practice_content.problem_type.id,)
        and event.concept_ids == (practice_content.concept.id,)
        and event.learning_outcome_ids == (practice_content.learning_outcome.id,)
        for event in publisher.events
    )


def test_real_mastery_publisher_updates_children_without_static_graph_mutation(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    second_concept = Concept(
        subject_id=practice_content.subject.id,
        code="GROUP-STATIC-GRAPH-TARGET",
        name="Static target",
        grade_level=12,
        order_index=99,
    )
    db_session.add(second_concept)
    db_session.flush()
    db_session.add_all([
        ConceptRelation(
            source_concept_id=practice_content.concept.id,
            target_concept_id=second_concept.id,
            relation_type=RelationType.PREREQUISITE,
        ),
        ProblemTypeConcept(
            problem_type_id=practice_content.problem_type.id,
            concept_id=practice_content.concept.id,
            weight=1.0,
            is_primary=True,
        ),
        ProblemTypeLearningOutcome(
            problem_type_id=practice_content.problem_type.id,
            learning_outcome_id=practice_content.learning_outcome.id,
            weight=1.0,
        ),
    ])
    db_session.commit()
    grouped = create_group(
        db_session, practice_content, _teacher(practice_user_factory, "mastery")
    )
    static_before = (
        list(db_session.execute(select(ConceptRelation.__table__))),
        list(db_session.execute(select(ProblemTypeConcept.__table__))),
        list(db_session.execute(select(ProblemTypeLearningOutcome.__table__))),
    )
    service = PracticeService(db_session)
    practice = _practice(service, student, practice_content)

    service.answer_group(student, practice.id, _group_answers(grouped.group.id, 4))

    concept_mastery = db_session.scalar(select(StudentConceptMastery))
    problem_mastery = db_session.scalar(select(StudentProblemTypeMastery))
    assert concept_mastery is not None and concept_mastery.attempt_count == 4
    assert problem_mastery is not None and problem_mastery.attempt_count == 4
    static_after = (
        list(db_session.execute(select(ConceptRelation.__table__))),
        list(db_session.execute(select(ProblemTypeConcept.__table__))),
        list(db_session.execute(select(ProblemTypeLearningOutcome.__table__))),
    )
    assert static_after == static_before


def test_third_evidence_failure_rolls_back_entire_group_and_mastery(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    grouped = create_group(
        db_session, practice_content, _teacher(practice_user_factory, "rollback")
    )
    service = PracticeService(db_session, evidence_publisher=FailOnThirdPublisher())
    practice = _practice(service, student, practice_content)

    with pytest.raises(RuntimeError, match="third child evidence failed"):
        service.answer_group(
            student, practice.id, _group_answers(grouped.group.id, 4)
        )

    assert db_session.scalar(select(func.count()).select_from(QuestionGroupAttempt)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupAttemptItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionAttempt)) == 0
    assert db_session.scalar(select(func.count()).select_from(StudentConceptMastery)) == 0
    assert db_session.scalar(select(func.count()).select_from(StudentProblemTypeMastery)) == 0
    assert db_session.scalar(select(func.count()).select_from(ReviewSchedule)) == 0


def test_duplicate_group_submission_is_stable_and_does_not_duplicate_rows(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    grouped = create_group(
        db_session, practice_content, _teacher(practice_user_factory, "duplicate")
    )
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(service, student, practice_content)
    data = _group_answers(grouped.group.id, 4)
    service.answer_group(student, practice.id, data)

    with pytest.raises(ApplicationError) as error:
        service.answer_group(student, practice.id, data)

    assert error.value.status_code == 409
    assert error.value.code == "QUESTION_GROUP_ALREADY_ANSWERED"
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupAttempt)) == 1
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupAttemptItem)) == 4
    assert db_session.scalar(select(func.count()).select_from(QuestionAttempt)) == 4


def test_legacy_answer_rejects_grouped_child(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    grouped = create_group(
        db_session, practice_content, _teacher(practice_user_factory, "legacy")
    )
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(service, student, practice_content)

    with pytest.raises(ApplicationError) as error:
        service.answer(
            student,
            practice.id,
            PracticeAnswerCreate(
                question_id=grouped.children[0].id,
                student_answer="TRUE",
            ),
        )
    assert error.value.code == "QUESTION_NOT_ELIGIBLE"


def test_grouped_child_is_hidden_from_learning_but_visible_to_admin(
    db_session: Session,
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    author = _teacher(practice_user_factory, "staff-visibility")
    admin = practice_user_factory(Role.ADMIN, "group-admin@example.com")
    grouped = create_group(db_session, practice_content, author)
    child = grouped.children[0]
    service = QuestionService(db_session)

    approved = service.list(admin, status=QuestionStatus.APPROVED)
    assert child.id in {question.id for question in approved}
    assert service.get(admin, child.id).id == child.id

    with pytest.raises(ApplicationError) as error:
        service.get_approved_for_learning(child.id)
    assert error.value.code == "APPROVED_QUESTION_NOT_FOUND"

    standalone_ids = set(
        db_session.scalars(
            select(Question.id).where(
                Question.status == QuestionStatus.APPROVED,
                standalone_question_only(),
            )
        )
    )
    assert child.id not in standalone_ids
    assert practice_content.mcq.id in standalone_ids


def test_session_completion_considers_both_item_pools(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    author = _teacher(practice_user_factory, "completion")

    group_a = create_group(db_session, practice_content, author)
    service_a = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice_a = _practice(service_a, student, practice_content)
    service_a.answer_group(student, practice_a.id, _group_answers(group_a.group.id, 4))
    db_session.refresh(practice_a)
    assert practice_a.status == PracticeSessionStatus.ACTIVE


def test_answering_standalone_keeps_session_active_while_group_remains(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    create_group(db_session, practice_content, _teacher(practice_user_factory, "remain"))
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(service, student, practice_content)
    service.answer(
        student,
        practice.id,
        PracticeAnswerCreate(question_id=practice_content.mcq.id, student_answer="B"),
    )
    db_session.refresh(practice)
    assert practice.status == PracticeSessionStatus.ACTIVE


def test_group_answer_completes_when_both_pools_are_exhausted(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    grouped = create_group(
        db_session, practice_content, _teacher(practice_user_factory, "complete")
    )
    for question in (
        practice_content.mcq,
        practice_content.true_false,
        practice_content.short_answer,
        practice_content.open_response,
    ):
        question.status = QuestionStatus.DRAFT
    db_session.commit()
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(service, student, practice_content)

    service.answer_group(student, practice.id, _group_answers(grouped.group.id, 4))
    db_session.refresh(practice)
    assert practice.status == PracticeSessionStatus.COMPLETED


def test_standalone_answer_completes_when_both_pools_are_exhausted(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    for question in (
        practice_content.true_false,
        practice_content.short_answer,
        practice_content.open_response,
    ):
        question.status = QuestionStatus.DRAFT
    db_session.commit()
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(service, student, practice_content)

    service.answer(
        student,
        practice.id,
        PracticeAnswerCreate(
            question_id=practice_content.mcq.id,
            student_answer="B",
        ),
    )
    db_session.refresh(practice)
    assert practice.status == PracticeSessionStatus.COMPLETED


def test_problem_type_and_concept_scope_both_must_match(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    grouped = create_group(
        db_session, practice_content, _teacher(practice_user_factory, "scope")
    )
    other_concept = Concept(
        subject_id=practice_content.subject.id,
        code="GROUP-SCOPE-OTHER",
        name="Other scope concept",
        grade_level=12,
        order_index=100,
    )
    db_session.add(other_concept)
    db_session.commit()
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(
        service,
        student,
        practice_content,
        problem_type_ids=[practice_content.problem_type.id],
        concept_ids=[other_concept.id],
    )

    with pytest.raises(ApplicationError) as error:
        service.answer_group(
            student, practice.id, _group_answers(grouped.group.id, 4)
        )
    assert error.value.code == "QUESTION_GROUP_NOT_ELIGIBLE"


def test_problem_type_scope_must_match_at_least_one_child(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    grouped = create_group(
        db_session, practice_content, _teacher(practice_user_factory, "pt-scope")
    )
    other_problem_type = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code="GROUP-SCOPE-UNMAPPED-PT",
        name="Unmapped group scope",
        description="A target absent from all group children.",
        order_index=101,
    )
    db_session.add(other_problem_type)
    db_session.commit()
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(
        service,
        student,
        practice_content,
        problem_type_ids=[other_problem_type.id],
        concept_ids=[practice_content.concept.id],
    )

    with pytest.raises(ApplicationError) as error:
        service.answer_group(
            student, practice.id, _group_answers(grouped.group.id, 4)
        )
    assert error.value.code == "QUESTION_GROUP_NOT_ELIGIBLE"


def test_problem_type_and_concept_scope_may_match_different_children(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    grouped = create_group(
        db_session, practice_content, _teacher(practice_user_factory, "split-scope")
    )
    target_problem_type = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code="GROUP-SCOPE-SPLIT-PT",
        name="Split group scope problem type",
        description="Mapped only to child a.",
        order_index=102,
    )
    target_concept = Concept(
        subject_id=practice_content.subject.id,
        code="GROUP-SCOPE-SPLIT-CONCEPT",
        name="Split group scope concept",
        grade_level=12,
        order_index=102,
    )
    db_session.add_all([target_problem_type, target_concept])
    db_session.flush()
    grouped.children[0].problem_type_links.append(
        QuestionProblemType(
            problem_type_id=target_problem_type.id,
            weight=0.5,
            is_primary=False,
        )
    )
    grouped.children[1].concept_links.append(
        QuestionConcept(concept_id=target_concept.id, weight=0.5)
    )
    db_session.commit()
    service = PracticeService(db_session, evidence_publisher=RecordingPublisher())
    practice = _practice(
        service,
        student,
        practice_content,
        problem_type_ids=[target_problem_type.id],
        concept_ids=[target_concept.id],
    )

    item = service.get_next_item(student, practice.id)
    assert item.item_type == "QUESTION_GROUP"
    assert item.question_group is not None
    assert item.question_group.id == grouped.group.id
