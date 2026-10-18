from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment,
    AssignmentMaterialItem,
    AssignmentMaterialItemConcept,
    AssignmentMaterialItemProblemType,
    AssignmentStudentQuestion,
    AssignmentType,
    StudentAssignment,
    StudentAssignmentMaterialItem,
    StudentAssignmentStatus,
)
from app.concepts.models import Concept
from app.curriculum.models import Chapter, ProblemType, Topic
from app.knowledge_gap.evidence_context import LearningEvidenceContextResolver
from app.learning_evidence.models import (
    LearningEvidenceEvent,
    LearningEvidenceSourceKind,
)
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.math_solutions.evidence_adapter import MathSolutionEvidenceAdapter
from app.math_solutions.models import (
    EvaluationDecision,
    EvaluationOverride,
    SolutionAttempt,
    SolutionStep,
)
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.review.models import ReviewSchedule
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


def _setup_taxonomy(db_session: Session):
    subject = Subject(code="MATH-12-DIAG", name="Toán 12 Chẩn đoán", grade_level=12)
    db_session.add(subject)
    db_session.flush()

    chapter = Chapter(subject_id=subject.id, code="CALCULUS_12", name="Đạo hàm và Ứng dụng", order_index=1)
    db_session.add(chapter)
    db_session.flush()

    topic = Topic(chapter_id=chapter.id, code="MONOTONICITY_TOPIC", name="Tính đơn điệu", order_index=1)
    db_session.add(topic)
    db_session.flush()

    problem_type = ProblemType(topic_id=topic.id, code="MONOTONICITY_PT", name="Xét tính đơn điệu hàm bậc ba", order_index=1)
    db_session.add(problem_type)

    concept = Concept(subject_id=subject.id, code="DERIVATIVE_CONCEPT", name="Đạo hàm hàm đa thức", order_index=1)
    db_session.add(concept)
    db_session.flush()

    return subject, chapter, topic, problem_type, concept


def test_learning_evidence_resolver_canonical_branch(db_session: Session):
    subject, chapter, topic, problem_type, concept = _setup_taxonomy(db_session)
    users = UserService(db_session)
    student_user = users.create_user(UserCreate(email="diag_stud1@example.com", password="Password123!", full_name="Student 1", role=Role.STUDENT))
    teacher_user = users.create_user(UserCreate(email="diag_teach1@example.com", password="Password123!", full_name="Teacher 1", role=Role.TEACHER))

    student = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    question = Question(
        subject_id=subject.id,
        content=r"Tìm các khoảng đơn điệu của hàm số $y = x^3 - 3x^2 - 9x + 2$.",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.5,
        correct_answer="Đồng biến trên (-inf, -1) và (3, +inf)",
        explanation="Chi tiết khảo sát hàm số",
        source_type="TEST",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        created_by=teacher_user.id,
    )
    db_session.add(question)
    db_session.flush()

    db_session.add(QuestionConcept(question_id=question.id, concept_id=concept.id, weight=1.0))
    db_session.add(QuestionProblemType(question_id=question.id, problem_type_id=problem_type.id, weight=1.0, is_primary=True))
    db_session.flush()

    practice = PracticeSession(
        student_id=student.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(practice)
    db_session.flush()

    now = datetime.now(timezone.utc)
    attempt = SolutionAttempt(
        student_id=student.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        question_id=question.id,
        practice_session_id=practice.id,
        mode="INDEPENDENT_SOLUTION",
        status="EVALUATED",
        total_score=0.40,
        is_correct=False,
        started_at=now - timedelta(minutes=10),
        submitted_at=now,
        evaluated_at=now,
    )
    db_session.add(attempt)
    db_session.flush()

    # Add solution steps
    db_session.add(SolutionStep(attempt_id=attempt.id, step_index=1, step_type="ASSUMPTION", content_latex=r"D = \mathbb{R}"))
    db_session.add(SolutionStep(attempt_id=attempt.id, step_index=2, step_type="DERIVATIVE_CALCULATION", content_latex=r"y' = 3x^2 - 6x - 9"))
    db_session.flush()

    decision = EvaluationDecision(
        attempt_id=attempt.id,
        decision_source="AUTOMATED_CONSENSUS",
        final_score=0.40,
        is_correct=False,
        confirmed_misconceptions=["SIGN_TABLE_QUADRATIC_RULE_INVERTED"],
        decided_at=now,
    )
    db_session.add(decision)
    db_session.flush()

    # Emit evidence using adapter
    adapter = MathSolutionEvidenceAdapter(db_session)
    event = adapter.emit_evidence_for_decision(decision.id)

    assert event is not None
    assert event.source_kind == LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION
    assert event.source_entity_id == decision.id
    assert event.score == 0.40
    assert event.is_correct is False
    assert decision.learning_evidence_event_id == event.id

    # Resolve context using LearningEvidenceContextResolver
    resolver = LearningEvidenceContextResolver(db_session)
    diag_context = resolver.resolve(event.id)

    assert diag_context is not None
    assert diag_context.student_id == student.id
    assert diag_context.subject_id == subject.id
    assert diag_context.primary_problem_type_id == problem_type.id
    assert diag_context.canonical_question is not None
    assert diag_context.canonical_question.id == question.id
    assert "Step 1 [ASSUMPTION]" in (diag_context.student_response or "")
    assert "Step 2 [DERIVATIVE_CALCULATION]" in (diag_context.student_response or "")


def test_learning_evidence_resolver_material_snapshot_branch(db_session: Session):
    subject, chapter, topic, problem_type, concept = _setup_taxonomy(db_session)
    users = UserService(db_session)
    student_user = users.create_user(UserCreate(email="diag_stud2@example.com", password="Password123!", full_name="Student 2", role=Role.STUDENT))
    teacher_user = users.create_user(UserCreate(email="diag_teach2@example.com", password="Password123!", full_name="Teacher 2", role=Role.TEACHER))

    student = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    from app.classes.models import Classroom
    classroom = Classroom(
        name="12A1 Diag",
        academic_year="2025-2026",
        grade_level=12,
        created_by=teacher_user.id,
    )
    db_session.add(classroom)
    db_session.flush()

    assignment = Assignment(
        classroom_id=classroom.id,
        subject_id=subject.id,
        title="Bài tập Đạo hàm Lớp",
        assignment_type=AssignmentType.SAME_SET,
        question_count=1,
        created_by=teacher_user.id,
    )
    db_session.add(assignment)
    db_session.flush()

    from app.teacher_materials.models import (
        TeacherMaterial,
        TeacherMaterialItem,
        TeacherMaterialStatus,
        MaterialItemExtractionStatus,
        MaterialEvaluationMode,
    )
    mat = TeacherMaterial(
        classroom_id=classroom.id,
        subject_id=subject.id,
        uploaded_by=teacher_user.id,
        title="PDF Giáo trình Đạo hàm",
        original_file_name="giao_trinh.pdf",
        mime_type="application/pdf",
        storage_key="diag-test-pdf-" + str(uuid4()),
        sha256="a" * 64,
        file_size_bytes=1024,
        status=TeacherMaterialStatus.READY,
    )
    db_session.add(mat)
    db_session.flush()

    t_item = TeacherMaterialItem(
        teacher_material_id=mat.id,
        order_index=1,
        content=r"Khảo sát hàm số $y = x^3 - 3x^2$ từ tài liệu PDF.",
        content_hash="b" * 64,
        extraction_status=MaterialItemExtractionStatus.READY,
        evaluation_mode=MaterialEvaluationMode.OPEN_RESPONSE,
    )
    db_session.add(t_item)
    db_session.flush()

    material_item = AssignmentMaterialItem(
        assignment_id=assignment.id,
        teacher_material_item_id=t_item.id,
        teacher_material_id=mat.id,
        order_index=1,
        content=r"Khảo sát hàm số $y = x^3 - 3x^2$ từ tài liệu PDF.",
        correct_answer="y' = 3x^2 - 6x",
        explanation="Đáp án chi tiết giáo viên soạn",
        snapshotted_at=datetime.now(timezone.utc),
        difficulty=0.6,
    )
    db_session.add(material_item)
    db_session.flush()

    db_session.add(AssignmentMaterialItemConcept(assignment_material_item_id=material_item.id, concept_id=concept.id, weight=1.0, confidence=1.0))
    db_session.add(AssignmentMaterialItemProblemType(assignment_material_item_id=material_item.id, problem_type_id=problem_type.id, weight=1.0, confidence=1.0, is_primary=True))
    db_session.flush()

    student_assignment = StudentAssignment(
        assignment_id=assignment.id,
        student_id=student.id,
        status=StudentAssignmentStatus.IN_PROGRESS,
    )
    db_session.add(student_assignment)
    db_session.flush()

    from app.practice.models import EvaluationStatus

    smi = StudentAssignmentMaterialItem(
        student_assignment_id=student_assignment.id,
        assignment_material_item_id=material_item.id,
        teacher_material_item_id=t_item.id,
        order_index=1,
        evaluation_status=EvaluationStatus.NEEDS_EVALUATION,
    )
    db_session.add(smi)
    db_session.flush()

    now = datetime.now(timezone.utc)
    attempt = SolutionAttempt(
        student_id=student.id,
        source_kind="TEACHER_MATERIAL",
        context_type="CLASSROOM_ASSIGNMENT",
        assignment_material_item_id=material_item.id,
        student_assignment_material_item_id=smi.id,
        assignment_id=assignment.id,
        student_assignment_id=student_assignment.id,
        mode="INDEPENDENT_SOLUTION",
        status="EVALUATED",
        total_score=0.80,
        is_correct=True,
        started_at=now - timedelta(minutes=5),
        submitted_at=now,
        evaluated_at=now,
    )
    db_session.add(attempt)
    db_session.flush()

    db_session.add(SolutionStep(attempt_id=attempt.id, step_index=1, step_type="DERIVATIVE_CALCULATION", content_latex=r"y' = 3x^2 - 6x"))
    db_session.flush()

    decision = EvaluationDecision(
        attempt_id=attempt.id,
        decision_source="AUTOMATED_CONSENSUS",
        final_score=0.80,
        is_correct=True,
        confirmed_misconceptions=[],
        decided_at=now,
    )
    db_session.add(decision)
    db_session.flush()

    adapter = MathSolutionEvidenceAdapter(db_session)
    event = adapter.emit_evidence_for_decision(decision.id)

    assert event.source_kind == LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION
    assert event.source_entity_id == decision.id

    resolver = LearningEvidenceContextResolver(db_session)
    diag_context = resolver.resolve(event.id)

    assert diag_context is not None
    assert diag_context.assignment_material_snapshot_id == material_item.id
    assert "Step 1 [DERIVATIVE_CALCULATION]" in (diag_context.student_response or "")
    assert diag_context.content == material_item.content


def test_anti_double_counting_and_mastery_calculation(db_session: Session):
    subject, chapter, topic, problem_type, concept = _setup_taxonomy(db_session)
    users = UserService(db_session)
    student_user = users.create_user(UserCreate(email="diag_stud3@example.com", password="Password123!", full_name="Student 3", role=Role.STUDENT))
    teacher_user = users.create_user(UserCreate(email="diag_teach3@example.com", password="Password123!", full_name="Teacher 3", role=Role.TEACHER))

    student = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    question = Question(
        subject_id=subject.id,
        content="Câu hỏi bài tập lớp",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.5,
        source_type="TEST",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        created_by=teacher_user.id,
    )
    db_session.add(question)
    db_session.flush()
    db_session.add(QuestionConcept(question_id=question.id, concept_id=concept.id, weight=1.0))
    db_session.add(QuestionProblemType(question_id=question.id, problem_type_id=problem_type.id, weight=1.0, is_primary=True))
    db_session.flush()

    from app.classes.models import Classroom
    classroom = Classroom(
        name="12A2",
        academic_year="2025-2026",
        grade_level=12,
        created_by=teacher_user.id,
    )
    db_session.add(classroom)
    db_session.flush()

    assignment = Assignment(
        classroom_id=classroom.id,
        subject_id=subject.id,
        title="BTVN Toán 12",
        assignment_type=AssignmentType.SAME_SET,
        question_count=1,
        created_by=teacher_user.id,
    )
    db_session.add(assignment)
    db_session.flush()

    sa = StudentAssignment(
        assignment_id=assignment.id,
        student_id=student.id,
        status=StudentAssignmentStatus.IN_PROGRESS,
    )
    db_session.add(sa)
    db_session.flush()

    asq = AssignmentStudentQuestion(
        student_assignment_id=sa.id,
        question_id=question.id,
        order_index=1,
    )
    db_session.add(asq)
    db_session.flush()

    now = datetime.now(timezone.utc)
    attempt = SolutionAttempt(
        student_id=student.id,
        source_kind="CANONICAL",
        context_type="CLASSROOM_ASSIGNMENT",
        question_id=question.id,
        assignment_student_question_id=asq.id,
        assignment_id=assignment.id,
        student_assignment_id=sa.id,
        mode="INDEPENDENT_SOLUTION",
        status="EVALUATED",
        total_score=0.40,
        is_correct=False,
        started_at=now - timedelta(minutes=15),
        submitted_at=now,
        evaluated_at=now,
    )
    db_session.add(attempt)
    db_session.flush()

    decision = EvaluationDecision(
        attempt_id=attempt.id,
        decision_source="AUTOMATED_CONSENSUS",
        final_score=0.40,
        is_correct=False,
        confirmed_misconceptions=["SIGN_TABLE_QUADRATIC_RULE_INVERTED"],
        decided_at=now,
    )
    db_session.add(decision)
    db_session.flush()

    adapter = MathSolutionEvidenceAdapter(db_session)
    event1 = adapter.emit_evidence_for_decision(decision.id)

    # 1. Verify idempotency
    event2 = adapter.emit_evidence_for_decision(decision.id)
    assert event1.id == event2.id

    # 2. Verify AssignmentStudentQuestion is synchronized
    db_session.refresh(asq)
    assert asq.score == 0.40
    assert asq.is_correct is False

    # 3. Verify exactly 1 LearningEvidenceEvent exists for this attempt
    total_events = db_session.scalars(
        select(LearningEvidenceEvent).where(
            LearningEvidenceEvent.source_kind == LearningEvidenceSourceKind.MATH_SOLUTION_EVALUATION,
            LearningEvidenceEvent.source_entity_id == decision.id,
        )
    ).all()
    assert len(total_events) == 1

    # 4. Verify Mastery updated according to DeterministicMasteryCalculationStrategy
    pt_mastery = db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == student.id,
            StudentProblemTypeMastery.problem_type_id == problem_type.id,
        )
    )
    assert pt_mastery is not None
    assert pt_mastery.attempt_count == 1
    # Mastery score grew according to strategy (score was 0.40, starting from 0.0)
    # formula: 0.0 + min(0.3, 0.22 * 1.0 * (1.1 - 0.3*0.5) * 1.0) * (0.40 - 0.0)
    # factor = 1.1 - 0.15 = 0.95; rate = 0.22 * 0.95 = 0.209; new_score = 0.209 * 0.40 = 0.0836
    assert 0.05 <= pt_mastery.mastery_score <= 0.15
    assert pt_mastery.confidence > 0.0

    # 5. Verify ReviewSchedule created with exactly 2.0 days interval
    schedule = db_session.scalar(
        select(ReviewSchedule).where(
            ReviewSchedule.student_id == student.id,
            ReviewSchedule.problem_type_id == problem_type.id,
        )
    )
    assert schedule is not None
    assert schedule.review_interval_days == 2.0
    expected_next = now + timedelta(days=2.0)
    sched_next = schedule.next_review_at
    if sched_next.tzinfo is None:
        sched_next = sched_next.replace(tzinfo=timezone.utc)
    assert abs((sched_next - expected_next).total_seconds()) < 5.0


def test_teacher_override_audit_ledger(db_session: Session):
    subject, chapter, topic, problem_type, concept = _setup_taxonomy(db_session)
    users = UserService(db_session)
    student_user = users.create_user(UserCreate(email="diag_stud4@example.com", password="Password123!", full_name="Student 4", role=Role.STUDENT))
    teacher_user = users.create_user(UserCreate(email="diag_teach4@example.com", password="Password123!", full_name="Teacher 4", role=Role.TEACHER))

    student = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    practice = PracticeSession(
        student_id=student.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(practice)
    db_session.flush()

    question = Question(
        subject_id=subject.id,
        content="Câu hỏi kiểm tra override",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.5,
        source_type="TEST",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        created_by=teacher_user.id,
    )
    db_session.add(question)
    db_session.flush()

    now = datetime.now(timezone.utc)
    attempt = SolutionAttempt(
        student_id=student.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        question_id=question.id,
        practice_session_id=practice.id,
        mode="INDEPENDENT_SOLUTION",
        status="EVALUATED",
        total_score=0.40,
        is_correct=False,
        started_at=now,
        submitted_at=now,
        evaluated_at=now,
    )
    db_session.add(attempt)
    db_session.flush()

    decision = EvaluationDecision(
        attempt_id=attempt.id,
        decision_source="AUTOMATED_CONSENSUS",
        final_score=0.40,
        is_correct=False,
        confirmed_misconceptions=["SIGN_TABLE_QUADRATIC_RULE_INVERTED"],
        decided_at=now,
    )
    db_session.add(decision)
    db_session.flush()

    adapter = MathSolutionEvidenceAdapter(db_session)
    event = adapter.emit_evidence_for_decision(decision.id)
    assert event.score == 0.40

    # Teacher overrides score from 0.40 to 0.75
    override = adapter.apply_teacher_override(
        decision.id,
        teacher_user.id,
        new_score=0.75,
        new_is_correct=True,
        reason="Học sinh có lập luận đúng ở phần biến thiên phụ, nâng điểm bài làm.",
    )

    assert override is not None
    assert override.override_version == 1
    assert override.previous_score == 0.40
    assert override.new_score == 0.75
    assert override.projection_status == "APPLIED"

    # Verify decision updated
    db_session.refresh(decision)
    assert decision.final_score == 0.75
    assert decision.is_correct is True
    assert decision.decision_source == "TEACHER_REVIEW"

    # Verify original LearningEvidenceEvent is append-only immutable (score not overwritten directly)
    db_session.refresh(event)
    assert event.score == 0.40
