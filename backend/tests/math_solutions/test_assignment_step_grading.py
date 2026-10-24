"""Assignment and Math Solution share one grading transaction and one score per item."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment, AssignmentMaterialItem, AssignmentStatus, AssignmentType,
    AssignmentStudentQuestion,
    StudentAssignment, StudentAssignmentMaterialItem, StudentAssignmentStatus,
)
from app.assignments.schemas import (
    AnswerSubmitItem, AssignmentSubmissionRequest, MaterialItemGradeRequest,
)
from app.assignments.service import AssignmentService
from app.assignments.teacher_grading_schemas import CanonicalQuestionGradeRequest
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.core.exceptions import ApplicationError
from app.learning_evidence.models import LearningEvidenceEvent, LearningEvidenceSourceKind
from app.math_solutions.evaluator_service import MathEvaluatorService
from app.math_solutions.models import EvaluationDecision, SolutionAttempt, SolutionRubric
from app.math_solutions.schemas import SolutionStepDraft
from app.math_solutions.service import MathSolutionService
from app.practice.models import EvaluationStatus
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teacher_materials.models import (
    MaterialEvaluationMode, MaterialItemExtractionStatus,
    TeacherMaterial, TeacherMaterialItem, TeacherMaterialStatus,
)
from app.teachers.models import TeacherProfile
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


def test_assignment_step_score_and_teacher_fallback_share_one_result(db_session: Session):
    users = UserService(db_session)
    teacher = users.create_user(UserCreate(
        email="step-assignment-teacher@example.com",
        password="Step-Assignment-Test-Password-2026!",
        full_name="Assignment Teacher", role=Role.TEACHER,
    ))
    student = users.create_user(UserCreate(
        email="step-assignment-student@example.com",
        password="Step-Assignment-Test-Password-2026!",
        full_name="Assignment Student", role=Role.STUDENT,
    ))
    teacher_profile = db_session.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == teacher.id)
    )
    student_profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    subject = Subject(code="MATH-STEP-ASG", name="Assignment step math", grade_level=12)
    room = Classroom(
        name="Step grading class", academic_year="2026-2027",
        grade_level=12, created_by=teacher.id,
    )
    db_session.add_all([subject, room])
    db_session.flush()
    db_session.add_all([
        TeacherClassroom(
            teacher_id=teacher_profile.id, classroom_id=room.id, role="OWNER",
        ),
        StudentEnrollment(
            student_id=student_profile.id, classroom_id=room.id,
            status=EnrollmentStatus.ACTIVE,
        ),
    ])
    now = datetime.now(timezone.utc)
    assignment = Assignment(
        classroom_id=room.id, subject_id=subject.id, title="Derivative steps",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED, question_count=4,
        start_at=now - timedelta(hours=1), due_at=now + timedelta(days=1),
        created_by=teacher.id,
    )
    material = TeacherMaterial(
        classroom_id=room.id, subject_id=subject.id, uploaded_by=teacher.id,
        title="Reviewed class worksheet", original_file_name="worksheet.pdf",
        mime_type="application/pdf", storage_key=f"test/{uuid4()}.pdf",
        sha256="a" * 64, file_size_bytes=100, page_count=1,
        status=TeacherMaterialStatus.READY,
    )
    db_session.add_all([assignment, material])
    db_session.flush()

    sources = []
    snapshots = []
    for index in range(2):
        source = TeacherMaterialItem(
            teacher_material_id=material.id, order_index=index,
            page_start=1, page_end=1,
            content="Old source text y = x^2",
            content_hash=str(index + 1) * 64,
            question_type=QuestionType.OPEN_RESPONSE,
            extraction_status=MaterialItemExtractionStatus.READY,
            evaluation_mode=MaterialEvaluationMode.OPEN_RESPONSE,
            raw_metadata={},
        )
        db_session.add(source)
        db_session.flush()
        snapshot = AssignmentMaterialItem(
            assignment_id=assignment.id,
            teacher_material_item_id=source.id,
            teacher_material_id=material.id,
            source_content_hash=source.content_hash,
            content="Find the derivative of y = x^3",
            order_index=index,
            snapshotted_at=now,
            question_type=QuestionType.OPEN_RESPONSE,
            evaluation_mode=MaterialEvaluationMode.OPEN_RESPONSE,
        )
        db_session.add(snapshot)
        db_session.flush()
        sources.append(source)
        snapshots.append(snapshot)

    assigned = StudentAssignment(
        assignment_id=assignment.id, student_id=student_profile.id,
        status=StudentAssignmentStatus.NOT_STARTED,
    )
    db_session.add(assigned)
    db_session.flush()
    canonical = Question(
        subject_id=subject.id, content="Find the derivative of y = x^3",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.5, source_type="TEST", exam_weight=0.5,
        status=QuestionStatus.APPROVED, created_by=teacher.id,
    )
    db_session.add(canonical)
    db_session.flush()
    assigned_question = AssignmentStudentQuestion(
        student_assignment_id=assigned.id,
        question_id=canonical.id,
        order_index=2,
    )
    canonical_rubric = SolutionRubric(
        question_id=canonical.id, title="Reviewed assigned question rubric",
        status="APPROVED", approved_by=teacher.id,
        criteria=[{"id": "derivative", "step_type": "DERIVATIVE_CALCULATION", "weight": 1.0}],
    )
    db_session.add_all([assigned_question, canonical_rubric])
    db_session.flush()
    pending_question = Question(
        subject_id=subject.id, content="Explain the derivative of y = x^4",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.5, source_type="TEST", exam_weight=0.5,
        status=QuestionStatus.APPROVED, created_by=teacher.id,
    )
    db_session.add(pending_question)
    db_session.flush()
    pending_question_item = AssignmentStudentQuestion(
        student_assignment_id=assigned.id,
        question_id=pending_question.id,
        order_index=3,
    )
    pending_question_rubric = SolutionRubric(
        question_id=pending_question.id, title="Reviewed pending question rubric",
        status="APPROVED", approved_by=teacher.id,
        criteria=[{"id": "derivative", "step_type": "DERIVATIVE_CALCULATION", "weight": 1.0}],
    )
    db_session.add_all([pending_question_item, pending_question_rubric])
    db_session.flush()
    items = []
    for index, (source, snapshot) in enumerate(zip(sources, snapshots)):
        item = StudentAssignmentMaterialItem(
            student_assignment_id=assigned.id,
            teacher_material_item_id=source.id,
            assignment_material_item_id=snapshot.id,
            order_index=index,
            evaluation_status=EvaluationStatus.NEEDS_EVALUATION,
        )
        rubric = SolutionRubric(
            assignment_material_item_id=snapshot.id,
            title=f"Reviewed derivative rubric {index}",
            status="APPROVED", approved_by=teacher.id,
            criteria=[{
                "id": "derivative",
                "step_type": "DERIVATIVE_CALCULATION",
                "weight": 1.0,
            }],
        )
        db_session.add_all([item, rubric])
        db_session.flush()
        items.append((item, rubric))
    db_session.commit()

    solutions = MathSolutionService(db_session)
    attempt_ids = []
    for index, (item, rubric) in enumerate(items):
        created = solutions.create(
            student.id,
            source_kind="TEACHER_MATERIAL",
            context_type="CLASSROOM_ASSIGNMENT",
            mode="INDEPENDENT_SOLUTION",
            create_idempotency_key=f"assignment-step-{index}",
            student_assignment_id=assigned.id,
            student_assignment_material_item_id=item.id,
            rubric_id=rubric.id,
        )
        attempt_id = UUID(created["id"])
        updated = solutions.add_step(
            student.id, attempt_id,
            expected_attempt_revision=created["attempt_revision_number"],
            client_action_id=uuid4(),
            draft=SolutionStepDraft(
                step_type="DERIVATIVE_CALCULATION" if index == 0 else "EXPLANATION",
                content_latex="y' = 3x^2" if index == 0 else None,
                explanation_text=None if index == 0 else "A verbal step needs teacher review.",
            ),
        )
        solutions.submit(
            student.id, attempt_id,
            expected_attempt_revision=updated["attempt_revision_number"],
            client_action_id=uuid4(),
        )
        attempt_ids.append(attempt_id)

    canonical_attempt = solutions.create(
        student.id,
        source_kind="CANONICAL",
        context_type="CLASSROOM_ASSIGNMENT",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key="assignment-canonical-step",
        question_id=canonical.id,
        student_assignment_id=assigned.id,
        assignment_student_question_id=assigned_question.id,
        rubric_id=canonical_rubric.id,
    )
    canonical_attempt_id = UUID(canonical_attempt["id"])
    canonical_updated = solutions.add_step(
        student.id, canonical_attempt_id,
        expected_attempt_revision=canonical_attempt["attempt_revision_number"],
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="DERIVATIVE_CALCULATION",
            content_latex="y' = 3x^2",
        ),
    )
    solutions.submit(
        student.id, canonical_attempt_id,
        expected_attempt_revision=canonical_updated["attempt_revision_number"],
        client_action_id=uuid4(),
    )

    pending_attempt = solutions.create(
        student.id,
        source_kind="CANONICAL",
        context_type="CLASSROOM_ASSIGNMENT",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key="assignment-canonical-pending",
        question_id=pending_question.id,
        student_assignment_id=assigned.id,
        assignment_student_question_id=pending_question_item.id,
        rubric_id=pending_question_rubric.id,
    )
    pending_attempt_id = UUID(pending_attempt["id"])
    pending_updated = solutions.add_step(
        student.id, pending_attempt_id,
        expected_attempt_revision=pending_attempt["attempt_revision_number"],
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="EXPLANATION",
            explanation_text="This mathematical reasoning needs teacher review.",
        ),
    )
    solutions.submit(
        student.id, pending_attempt_id,
        expected_attempt_revision=pending_updated["attempt_revision_number"],
        client_action_id=uuid4(),
    )
    with pytest.raises(ApplicationError) as conflicting:
        AssignmentService(db_session).submit_assignment(
            student.id, assignment.id,
            AssignmentSubmissionRequest(answers=[
                AnswerSubmitItem(question_id=canonical.id, student_answer="a different answer"),
            ]),
        )
    assert conflicting.value.code == "ASSIGNMENT_ANSWER_SOURCE_CONFLICT"
    db_session.rollback()
    with patch(
        "app.math_solutions.evidence_adapter.MathSolutionEvidenceAdapter.emit_evidence_for_decision",
        side_effect=RuntimeError("evidence write failed"),
    ):
        with pytest.raises(RuntimeError, match="evidence write failed"):
            AssignmentService(db_session).submit_assignment(
                student.id, assignment.id, AssignmentSubmissionRequest(answers=[]),
            )
    db_session.expire_all()
    assert db_session.get(StudentAssignment, assigned.id).status == StudentAssignmentStatus.NOT_STARTED
    assert db_session.scalars(select(EvaluationDecision)).all() == []
    assert db_session.scalars(select(LearningEvidenceEvent)).all() == []
    assert db_session.get(StudentAssignmentMaterialItem, items[0][0].id).score is None

    result = AssignmentService(db_session).submit_assignment(
        student.id, assignment.id, AssignmentSubmissionRequest(answers=[]),
    )
    db_session.expire_all()
    graded = db_session.get(StudentAssignmentMaterialItem, items[0][0].id)
    pending = db_session.get(StudentAssignmentMaterialItem, items[1][0].id)
    assert result.status == StudentAssignmentStatus.SUBMITTED
    assert result.score is None
    assert [row.score for row in result.results] == [1.0, None, 1.0, None]
    assert graded.score == 1.0
    assert graded.evaluation_status == EvaluationStatus.EVALUATED
    assert pending.score is None
    assert pending.evaluation_status == EvaluationStatus.NEEDS_EVALUATION
    assert db_session.get(SolutionAttempt, canonical_attempt_id).status == "EVALUATED"
    assert db_session.get(SolutionAttempt, pending_attempt_id).status == "SUBMITTED"
    assert db_session.get(SolutionAttempt, attempt_ids[0]).status == "EVALUATED"
    assert db_session.get(SolutionAttempt, attempt_ids[1]).status == "SUBMITTED"
    assert db_session.scalar(select(EvaluationDecision).where(
        EvaluationDecision.attempt_id == attempt_ids[1]
    )) is None
    evidence = list(db_session.scalars(select(LearningEvidenceEvent)).all())
    assert len(evidence) == 2
    assert all(row.source_kind == LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION for row in evidence)

    with pytest.raises(ApplicationError) as exc:
        AssignmentService(db_session).grade_material_item(
            teacher.id, assignment.id, student_profile.id, graded.id,
            MaterialItemGradeRequest(score=0.0, is_correct=False),
        )
    assert exc.value.code == "MATERIAL_ITEM_ALREADY_EVALUATED"

    with patch(
        "app.assignments.service.LearningEvidencePublisher.publish",
        side_effect=RuntimeError("material evidence failed"),
    ):
        with pytest.raises(RuntimeError, match="material evidence failed"):
            AssignmentService(db_session).grade_material_item(
                teacher.id, assignment.id, student_profile.id, pending.id,
                MaterialItemGradeRequest(score=0.5, is_correct=False),
            )
    db_session.expire_all()
    assert db_session.get(StudentAssignmentMaterialItem, pending.id).score is None
    assert db_session.get(StudentAssignment, assigned.id).status == StudentAssignmentStatus.SUBMITTED

    teacher_grade = AssignmentService(db_session).grade_material_item(
        teacher.id, assignment.id, student_profile.id, pending.id,
        MaterialItemGradeRequest(score=0.5, is_correct=False, feedback="Review the method."),
    )
    assert teacher_grade.assignment_score is None
    assert teacher_grade.assignment_status == StudentAssignmentStatus.SUBMITTED

    grade_data = CanonicalQuestionGradeRequest(
        score=0.25, is_correct=False, feedback="Check the derivative rule.",
    )
    with pytest.raises(ApplicationError) as student_forbidden:
        AssignmentService(db_session).grade_canonical_item(
            student.id, assignment.id, student_profile.id,
            pending_question_item.id, grade_data,
        )
    assert student_forbidden.value.status_code == 403

    unrelated_teacher = users.create_user(UserCreate(
        email="unrelated-step-teacher@example.com",
        password="Step-Assignment-Test-Password-2026!",
        full_name="Unrelated Teacher", role=Role.TEACHER,
    ))
    with pytest.raises(ApplicationError) as unrelated:
        AssignmentService(db_session).grade_canonical_item(
            unrelated_teacher.id, assignment.id, student_profile.id,
            pending_question_item.id, grade_data,
        )
    assert unrelated.value.status_code == 403

    with patch(
        "app.assignments.service.LearningEvidencePublisher.publish",
        side_effect=RuntimeError("teacher evidence failed"),
    ):
        with pytest.raises(RuntimeError, match="teacher evidence failed"):
            AssignmentService(db_session).grade_canonical_item(
                teacher.id, assignment.id, student_profile.id,
                pending_question_item.id, grade_data,
            )
    db_session.expire_all()
    assert db_session.get(AssignmentStudentQuestion, pending_question_item.id).score is None
    assert db_session.get(StudentAssignment, assigned.id).status == StudentAssignmentStatus.SUBMITTED
    graded_question = AssignmentService(db_session).grade_canonical_item(
        teacher.id, assignment.id, student_profile.id,
        pending_question_item.id, grade_data,
    )
    assert graded_question.assignment_score == 6.88
    assert graded_question.assignment_status == StudentAssignmentStatus.GRADED
    with pytest.raises(ApplicationError) as repeated_grade:
        AssignmentService(db_session).grade_canonical_item(
            teacher.id, assignment.id, student_profile.id,
            pending_question_item.id, grade_data,
        )
    assert repeated_grade.value.code == "QUESTION_NOT_PENDING"
    with pytest.raises(ApplicationError) as repeated:
        AssignmentService(db_session).submit_assignment(
            student.id, assignment.id, AssignmentSubmissionRequest(answers=[]),
        )
    assert repeated.value.code == "ASSIGNMENT_ALREADY_SUBMITTED"
    db_session.expire_all()
    with pytest.raises(ApplicationError) as double_score:
        MathEvaluatorService(db_session).evaluate_attempt(pending_attempt_id)
    assert double_score.value.code == "GRADING_ASSIGNMENT_NOT_SUBMITTED"
    evidence = list(db_session.scalars(select(LearningEvidenceEvent)).all())
    assert len(evidence) == 4
    assert {row.source_kind for row in evidence} == {
        LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION,
        LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM,
        LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION,
    }
    teacher_evidence = next(
        row for row in evidence
        if row.source_kind == LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION
    )
    assert teacher_evidence.event_metadata["graded_by"] == str(teacher.id)
    assert teacher_evidence.event_metadata["feedback"] == "Check the derivative rule."