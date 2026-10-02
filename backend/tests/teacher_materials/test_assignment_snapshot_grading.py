from hashlib import sha256

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import AssignmentMaterialItem, AssignmentType, StudentAssignmentStatus, StudentAssignmentMaterialItem
from app.assignments.schemas import (
    AnswerSubmitItem,
    AssignmentCreate,
    AssignmentSubmissionRequest,
    MaterialItemGradeRequest,
)
from app.assignments.service import AssignmentService
from app.core.exceptions import ApplicationError
from app.learning_evidence.models import LearningEvidenceEvent, LearningEvidenceSourceKind
from app.knowledge_gap.evidence_context import LearningEvidenceContextResolver
from app.knowledge_gap.models import RootCauseDiagnosis
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.models import EvaluationStatus
from app.questions.models import Question, QuestionOption, QuestionStatus, QuestionType
from app.teacher_materials.models import MaterialEvaluationMode, MaterialItemExtractionStatus
from app.teacher_materials.schemas import MaterialOptionInput, TeacherMaterialItemUpdate

from tests.teacher_materials.test_teacher_materials import setup_domain, upload_ready


def _assignment(domain, session: Session, item_id, question_ids=None):
    service = AssignmentService(session)
    created = service.create_assignment(
        domain.teacher.id,
        AssignmentCreate(
            classroom_id=domain.classroom.id,
            subject_id=domain.subject.id,
            title="Frozen worksheet",
            assignment_type=AssignmentType.SAME_SET,
            question_count=1,
            teacher_material_item_ids=[item_id],
            question_ids=question_ids,
        ),
    )
    service.publish_assignment(domain.teacher.id, created.id)
    return service, created.id


def _review_mode(domain, item, mode: MaterialEvaluationMode) -> None:
    update = TeacherMaterialItemUpdate(
        evaluation_mode=mode,
        question_type=QuestionType.OPEN_RESPONSE if mode == MaterialEvaluationMode.OPEN_RESPONSE else QuestionType.MULTIPLE_CHOICE,
        correct_answer=None if mode == MaterialEvaluationMode.OPEN_RESPONSE else "A",
    )
    domain.service.update_item(domain.teacher.id, item.id, update)
    domain.service.update_item(
        domain.teacher.id, item.id, TeacherMaterialItemUpdate(content_reviewed=True)
    )
    domain.service.mark_ready(domain.teacher.id, item.teacher_material_id)


def test_published_snapshot_survives_source_edit_and_drives_evidence(db_session, tmp_path):
    domain = setup_domain(db_session, tmp_path)
    _, item = upload_ready(domain, db_session)
    service, assignment_id = _assignment(domain, db_session, item.id)
    before = service.get_student_assignment(domain.student.id, assignment_id).questions[0]
    old_hash = item.content_hash
    domain.service.update_item(
        domain.teacher.id,
        item.id,
        TeacherMaterialItemUpdate(
            content="Rewritten question",
            correct_answer="B",
            difficulty=0.9,
            options=[
                MaterialOptionInput(label="A", content="New wrong", order_index=0),
                MaterialOptionInput(label="B", content="New correct", order_index=1),
            ],
        ),
    )
    item = domain.service._item(domain.teacher.id, item.id)
    assert item.extraction_status == MaterialItemExtractionStatus.NEEDS_REVIEW
    assert not any(mapping.status.value == "CONFIRMED" for mapping in item.concept_mappings)
    after = service.get_student_assignment(domain.student.id, assignment_id).questions[0]
    assert (after.content, after.difficulty, [(o.label, o.content) for o in after.options]) == (
        before.content,
        before.difficulty,
        [(o.label, o.content) for o in before.options],
    )
    result = service.submit_assignment(
        domain.student.id,
        assignment_id,
        AssignmentSubmissionRequest(
            answers=[AnswerSubmitItem(teacher_material_item_id=item.id, student_answer="A")]
        ),
    )
    assert result.score == 10
    event = db_session.scalar(
        select(LearningEvidenceEvent).where(
            LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM
        )
    )
    assert event.difficulty == 0.5
    assert event.event_metadata["snapshot_content_hash"] == old_hash
    assert event.event_metadata["original_teacher_material_item_id"] == str(item.id)
    assert event.event_metadata["original_teacher_material_id"] == str(item.teacher_material_id)
    assert event.event_metadata["grading_source"] == "AUTO"
    assert event.concepts[0].concept_id == domain.concept.id
    assert event.problem_types[0].problem_type_id == domain.pt.id
    assert event.problem_types[0].is_primary
    assert item.content_hash != old_hash
    from app.assignments.material_snapshot import snapshot_material_item

    frozen = db_session.get(AssignmentMaterialItem, before.assignment_material_item_id)
    with pytest.raises(ApplicationError) as immutable:
        snapshot_material_item(db_session, frozen, item)
    assert immutable.value.code == "MATERIAL_SNAPSHOT_IMMUTABLE"


def test_wrong_material_evidence_diagnoses_from_immutable_snapshot(db_session, tmp_path):
    domain = setup_domain(db_session, tmp_path)
    _, item = upload_ready(domain, db_session)
    service, assignment_id = _assignment(domain, db_session, item.id)
    assigned = service.get_student_assignment(domain.student.id, assignment_id).questions[0]
    frozen_content = assigned.content
    domain.service.update_item(
        domain.teacher.id,
        item.id,
        TeacherMaterialItemUpdate(content="Mutable source rewritten after publish"),
    )
    service.submit_assignment(
        domain.student.id,
        assignment_id,
        AssignmentSubmissionRequest(
            answers=[AnswerSubmitItem(teacher_material_item_id=item.id, student_answer="B")]
        ),
    )
    event = db_session.scalar(
        select(LearningEvidenceEvent).where(
            LearningEvidenceEvent.source_kind
            == LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM
        )
    )
    assert event is not None
    diagnosis = db_session.scalar(
        select(RootCauseDiagnosis).where(
            RootCauseDiagnosis.learning_evidence_event_id == event.id
        )
    )
    assert diagnosis is not None
    context = LearningEvidenceContextResolver(db_session).resolve(event.id)
    assert context.content == frozen_content
    assert context.content != "Mutable source rewritten after publish"
    assert str(context.assignment_material_snapshot_id) == diagnosis.diagnosis_metadata["snapshot_id"]


@pytest.mark.parametrize("mode", [MaterialEvaluationMode.TEACHER_REVIEW, MaterialEvaluationMode.OPEN_RESPONSE])
def test_teacher_grade_pending_once_and_update_mastery(db_session, tmp_path, mode):
    domain = setup_domain(db_session, tmp_path)
    _, item = upload_ready(domain, db_session)
    _review_mode(domain, item, mode)
    service, assignment_id = _assignment(domain, db_session, item.id)
    read = service.get_student_assignment(domain.student.id, assignment_id)
    student_item_id = read.questions[0].student_material_item_id
    result = service.submit_assignment(
        domain.student.id,
        assignment_id,
        AssignmentSubmissionRequest(answers=[
            AnswerSubmitItem(
                teacher_material_item_id=item.id,
                student_answer="My reasoning",
                response_time_seconds=32,
                hint_count=2,
            )
        ]),
    )
    assert result.score is None
    assert result.status == StudentAssignmentStatus.SUBMITTED
    assert db_session.scalar(select(LearningEvidenceEvent)) is None
    assert db_session.scalar(select(RootCauseDiagnosis)) is None
    student_item = db_session.get(StudentAssignmentMaterialItem, student_item_id)
    assert student_item.score is None
    assert student_item.evaluation_status in (
        EvaluationStatus.NEEDS_TEACHER_REVIEW,
        EvaluationStatus.NEEDS_EVALUATION,
    )
    with pytest.raises(ApplicationError) as unauthorized:
        service.grade_material_item(
            domain.outsider.id, assignment_id, domain.student_profile.id,
            student_item_id, MaterialItemGradeRequest(score=0.8, is_correct=True),
        )
    assert unauthorized.value.status_code == 403
    grade = service.grade_material_item(
        domain.teacher.id,
        assignment_id,
        domain.student_profile.id,
        student_item_id,
        MaterialItemGradeRequest(score=0.8, is_correct=True, feedback="Good reasoning"),
    )
    assert grade.assignment_score == 8
    assert grade.assignment_status == StudentAssignmentStatus.GRADED
    assert grade.graded_by == domain.teacher.id
    assert grade.feedback == "Good reasoning"
    event = db_session.scalar(
        select(LearningEvidenceEvent).where(
            LearningEvidenceEvent.source_entity_id == student_item_id
        )
    )
    assert event is not None
    assert event.event_metadata["grading_source"] == "TEACHER"
    assert event.response_time_seconds == 32 and event.hint_count == 2
    assert db_session.scalar(select(StudentConceptMastery)).attempt_count == 1


def test_pending_material_creates_diagnosis_only_after_wrong_teacher_grade(
    db_session, tmp_path
):
    domain = setup_domain(db_session, tmp_path)
    _, item = upload_ready(domain, db_session)
    _review_mode(domain, item, MaterialEvaluationMode.TEACHER_REVIEW)
    service, assignment_id = _assignment(domain, db_session, item.id)
    student_item_id = service.get_student_assignment(
        domain.student.id, assignment_id
    ).questions[0].student_material_item_id
    service.submit_assignment(
        domain.student.id,
        assignment_id,
        AssignmentSubmissionRequest(
            answers=[
                AnswerSubmitItem(
                    teacher_material_item_id=item.id,
                    student_answer="Reasoning pending review",
                )
            ]
        ),
    )
    assert db_session.scalar(select(RootCauseDiagnosis)) is None
    service.grade_material_item(
        domain.teacher.id,
        assignment_id,
        domain.student_profile.id,
        student_item_id,
        MaterialItemGradeRequest(score=0.0, is_correct=False),
    )
    diagnosis = db_session.scalar(select(RootCauseDiagnosis))
    assert diagnosis is not None
    assert diagnosis.learning_evidence_event_id == db_session.scalar(
        select(LearningEvidenceEvent.id)
    )
    assert db_session.scalar(select(StudentProblemTypeMastery)).attempt_count == 1
    with pytest.raises(ApplicationError) as duplicate:
        service.grade_material_item(
            domain.teacher.id, assignment_id, domain.student_profile.id,
            student_item_id, MaterialItemGradeRequest(score=0.1, is_correct=False),
        )
    assert duplicate.value.status_code == 409
    assert db_session.query(LearningEvidenceEvent).count() == 1
    assert db_session.scalar(select(StudentConceptMastery)).attempt_count == 1


def test_mixed_assignment_order_and_pending_final_score(db_session, tmp_path):
    domain = setup_domain(db_session, tmp_path)
    _, item = upload_ready(domain, db_session)
    _review_mode(domain, item, MaterialEvaluationMode.TEACHER_REVIEW)
    content = "Canonical approved question"
    question = Question(
        subject_id=domain.subject.id,
        content=content,
        content_hash=sha256(content.casefold().encode()).hexdigest(),
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=0.4,
        correct_answer="A",
        source_type="CURRICULUM",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        created_by=domain.teacher.id,
    )
    db_session.add(question)
    db_session.flush()
    db_session.add_all([
        QuestionOption(question_id=question.id, label=label, content=label, order_index=index)
        for index, label in enumerate(("A", "B"))
    ])
    db_session.commit()
    service, assignment_id = _assignment(domain, db_session, item.id, [question.id])
    read = service.get_student_assignment(domain.student.id, assignment_id)
    assert [(q.source_kind, q.order_index) for q in read.questions] == [
        ("CANONICAL_QUESTION", 0),
        ("TEACHER_MATERIAL_ITEM", 1),
    ]
    result = service.submit_assignment(
        domain.student.id,
        assignment_id,
        AssignmentSubmissionRequest(answers=[
            AnswerSubmitItem(question_id=question.id, student_answer="A"),
            AnswerSubmitItem(teacher_material_item_id=item.id, student_answer="Reasoning"),
        ]),
    )
    assert result.score is None
    grade = service.grade_material_item(
        domain.teacher.id,
        assignment_id,
        domain.student_profile.id,
        read.questions[1].student_material_item_id,
        MaterialItemGradeRequest(score=0.6, is_correct=False),
    )
    assert grade.assignment_score == 8
    assert grade.assignment_status == StudentAssignmentStatus.GRADED

def test_migration_backfills_existing_published_assignment(db_session, db_engine, tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import MetaData, Table

    from tests.migrations import load_migration

    domain = setup_domain(db_session, tmp_path)
    _, item = upload_ready(domain, db_session)
    _, assignment_id = _assignment(domain, db_session, item.id)
    db_session.expunge_all()
    db_session.close()
    migration = load_migration("0033_material_assignment_snapshot")
    with db_engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            migration.upgrade()
        metadata = MetaData()
        links = Table("assignment_material_items", metadata, autoload_with=connection)
        student_items = Table("student_assignment_material_items", metadata, autoload_with=connection)
        options = Table("assignment_material_item_options", metadata, autoload_with=connection)
        link = connection.execute(
            select(links).where(links.c.assignment_id == assignment_id)
        ).mappings().one()
        student_item = connection.execute(select(student_items)).mappings().one()
        assert link["content"] == item.content
        assert link["source_content_hash"] == item.content_hash
        assert student_item["assignment_material_item_id"] == link["id"]
        assert connection.execute(
            select(options).where(options.c.assignment_material_item_id == link["id"])
        ).mappings().all()

def test_teacher_grading_api_and_persisted_mapping_read(
    db_session, db_client, settings, tmp_path
):
    from uuid import uuid4

    from app.auth.schemas import LoginRequest
    from app.auth.service import AuthService
    from tests.teacher_materials.test_teacher_materials import PASSWORD

    domain = setup_domain(db_session, tmp_path)
    material, item = upload_ready(domain, db_session)
    mapping_response = db_client.get(
        f"/teacher-materials/{material.id}/items",
        headers={
            "Authorization": "Bearer " + AuthService(db_session, settings).login(
                LoginRequest(email=domain.teacher.email, password=PASSWORD)
            ).access_token
        },
    )
    assert mapping_response.status_code == 200, mapping_response.text
    mapped = mapping_response.json()[0]
    assert mapped["problem_type_mappings"][0]["problem_type_id"] == str(domain.pt.id)
    assert mapped["concept_mappings"][0]["concept_id"] == str(domain.concept.id)
    assert mapped["learning_outcome_mappings"][0]["learning_outcome_id"] == str(domain.lo.id)

    _review_mode(domain, item, MaterialEvaluationMode.TEACHER_REVIEW)
    service, assignment_id = _assignment(domain, db_session, item.id)
    student_item_id = service.get_student_assignment(
        domain.student.id, assignment_id
    ).questions[0].student_material_item_id
    service.submit_assignment(
        domain.student.id,
        assignment_id,
        AssignmentSubmissionRequest(
            answers=[AnswerSubmitItem(
                teacher_material_item_id=item.id, student_answer="Reasoning"
            )]
        ),
    )
    teacher_token = AuthService(db_session, settings).login(
        LoginRequest(email=domain.teacher.email, password=PASSWORD)
    ).access_token
    endpoint = (
        f"/teacher/assignments/{assignment_id}/students/"
        f"{domain.student_profile.id}/material-items/{student_item_id}/grade"
    )
    headers = {"Authorization": f"Bearer {teacher_token}"}
    wrong = db_client.post(
        endpoint.replace(str(domain.student_profile.id), str(uuid4())),
        json={"score": 0.75, "is_correct": True},
        headers=headers,
    )
    assert wrong.status_code == 404
    grade = db_client.post(
        endpoint,
        json={"score": 0.75, "is_correct": True, "feedback": "Reviewed"},
        headers=headers,
    )
    assert grade.status_code == 200, grade.text
    assert grade.json()["assignment_score"] == 7.5
    assert grade.json()["assignment_status"] == "GRADED"
    assert db_client.post(
        endpoint,
        json={"score": 0.3, "is_correct": False},
        headers=headers,
    ).status_code == 409

def test_source_edit_between_draft_and_publish_blocks_snapshot(db_session, tmp_path):
    domain = setup_domain(db_session, tmp_path)
    _, item = upload_ready(domain, db_session)
    service = AssignmentService(db_session)
    draft = service.create_assignment(
        domain.teacher.id,
        AssignmentCreate(
            classroom_id=domain.classroom.id,
            subject_id=domain.subject.id,
            title="Draft before edit",
            assignment_type=AssignmentType.SAME_SET,
            question_count=1,
            teacher_material_item_ids=[item.id],
        ),
    )
    domain.service.update_item(
        domain.teacher.id,
        item.id,
        TeacherMaterialItemUpdate(content="Changed before publish"),
    )
    with pytest.raises(ApplicationError) as error:
        service.publish_assignment(domain.teacher.id, draft.id)
    assert error.value.code == "MATERIAL_ITEM_NOT_READY"
