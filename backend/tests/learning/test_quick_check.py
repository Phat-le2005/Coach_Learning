from datetime import date, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, ProblemTypeConcept, Topic
from app.learning.models import (
    ConceptSignalLevel,
    QuickCheckQuestionRole,
    QuickCheckSession,
    QuickCheckVerdict,
)
from app.learning.policy import QuickCheckPolicy, QuickCheckThresholds
from app.learning.schemas import QuickCheckStartRequest
from app.learning.service import QuickCheckService
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.practice.models import PracticeSessionStatus, PracticeSessionType
from app.practice.schemas import PracticeAnswerCreate
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "QuickCheck-Secret-2026!"


def _create_user(session: Session, role: Role, email: str) -> User:
    return UserService(session).create_user(
        UserCreate(email=email, password=TEST_PASSWORD, full_name=f"{role.value} User", role=role)
    )


def _auth_headers(session: Session, settings: Settings, user: User) -> dict[str, str]:
    tokens = AuthService(session, settings).login(
        LoginRequest(email=user.email, password=TEST_PASSWORD)
    )
    return {"Authorization": f"Bearer {tokens.access_token}"}


def _create_curriculum_and_classroom(
    session: Session, prefix: str = "QC"
) -> tuple[Subject, ProblemType, ProblemType, Concept, Concept, LearningOutcome, Classroom, User, User]:
    teacher_user = _create_user(session, Role.TEACHER, f"{prefix.lower()}.teacher@example.com")
    student_user = _create_user(session, Role.STUDENT, f"{prefix.lower()}.student@example.com")
    teacher_profile = session.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == teacher_user.id)
    )
    student_profile = session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student_user.id)
    )

    subject = Subject(code=f"{prefix}-SUB", name=f"{prefix} Subject", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{prefix}-CHP", name="Chapter", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{prefix}-TOP", name="Topic", order_index=0)
    session.add(topic)
    session.flush()

    pt1 = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT1",
        name="Problem Type 1",
        order_index=0,
        is_active=True,
    )
    pt2 = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT2",
        name="Problem Type 2",
        order_index=1,
        is_active=True,
    )
    session.add_all([pt1, pt2])
    session.flush()

    concept1 = Concept(
        subject_id=subject.id, code=f"{prefix}-CON1", name="Concept 1", order_index=0
    )
    concept_pre = Concept(
        subject_id=subject.id, code=f"{prefix}-CON-PRE", name="Prerequisite Concept", order_index=1
    )
    session.add_all([concept1, concept_pre])
    session.flush()

    # Link PT1 to Concept 1
    session.add(ProblemTypeConcept(problem_type_id=pt1.id, concept_id=concept1.id, weight=1.0, is_primary=True))
    session.add(ProblemTypeConcept(problem_type_id=pt2.id, concept_id=concept1.id, weight=1.0, is_primary=True))

    lo = LearningOutcome(
        subject_id=subject.id,
        code=f"{prefix}-LO",
        description="Learning outcome",
        grade_level=12,
        order_index=0,
    )
    session.add(lo)
    session.flush()

    classroom = Classroom(
        name=f"{prefix}-12A",
        academic_year="2025-2026",
        grade_level=12,
        created_by=teacher_user.id,
    )
    classroom.teacher_assignments.append(
        TeacherClassroom(teacher_id=teacher_profile.id, role="OWNER")
    )
    classroom.student_enrollments.append(
        StudentEnrollment(student_id=student_profile.id, status=EnrollmentStatus.ACTIVE)
    )
    session.add(classroom)
    session.commit()

    return subject, pt1, pt2, concept1, concept_pre, lo, classroom, teacher_user, student_user


def _create_question(
    session: Session,
    subject: Subject,
    creator_id: UUID,
    difficulty: float,
    content: str,
    pt: ProblemType,
    concept: Concept,
    lo: LearningOutcome,
    correct_answer: str = "A",
    cognitive_level: CognitiveLevel | None = None,
) -> Question:
    q = Question(
        subject_id=subject.id,
        content=content,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=difficulty,
        correct_answer=correct_answer,
        explanation="Standard explanation",
        source_type="TEST",
        source_reference="qc-test",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        cognitive_level=cognitive_level,
        created_by=creator_id,
        options=[
            QuestionOption(label="A", content="Answer A", order_index=0),
            QuestionOption(label="B", content="Answer B", order_index=1),
        ],
    )
    q.problem_type_links.append(
        QuestionProblemType(problem_type_id=pt.id, weight=1.0, is_primary=True)
    )
    q.concept_links.append(QuestionConcept(concept_id=concept.id, weight=1.0))
    q.learning_outcome_links.append(QuestionLearningOutcome(learning_outcome_id=lo.id, weight=1.0))
    session.add(q)
    session.commit()
    session.refresh(q)
    return q


def test_active_plan_required(db_session: Session) -> None:
    subject, pt1, pt2, c1, c_pre, lo, classroom, teacher, student = (
        _create_curriculum_and_classroom(db_session, "REQ")
    )
    service = QuickCheckService(db_session)

    # 1. No active plan exists
    with pytest.raises(ApplicationError) as exc_info:
        service.start_quick_check(student, QuickCheckStartRequest(subject_id=subject.id))
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "ACTIVE_TEACHING_PLAN_REQUIRED"

    # 2. Teaching plan is PLANNED, not ACTIVE
    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.PLANNED,
        created_by=teacher.id,
        items=[TeachingPlanItem(problem_type_id=pt1.id, priority=1, order_index=0)],
    )
    db_session.add(plan)
    db_session.commit()

    with pytest.raises(ApplicationError) as exc_info:
        service.start_quick_check(student, QuickCheckStartRequest(subject_id=subject.id))
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "ACTIVE_TEACHING_PLAN_REQUIRED"

    # 3. Student not enrolled in specific classroom
    outsider_student = _create_user(db_session, Role.STUDENT, "outsider@example.com")
    with pytest.raises(ApplicationError) as exc_info:
        service.start_quick_check(
            outsider_student,
            QuickCheckStartRequest(subject_id=subject.id, classroom_id=classroom.id),
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "CLASSROOM_ACCESS_DENIED"


def test_question_coverage_and_roles(db_session: Session) -> None:
    subject, pt1, pt2, c1, c_pre, lo, classroom, teacher, student = (
        _create_curriculum_and_classroom(db_session, "COV")
    )

    # Active plan with 2 problem types
    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=teacher.id,
        items=[
            TeachingPlanItem(problem_type_id=pt1.id, priority=2, order_index=0),
            TeachingPlanItem(problem_type_id=pt2.id, priority=1, order_index=1),
        ],
    )
    db_session.add(plan)
    db_session.commit()

    # Create questions for PT1 & PT2: understanding (difficulty < 0.5) and application (difficulty >= 0.5)
    _create_question(db_session, subject, teacher.id, 0.30, "Q_PT1_Und", pt1, c1, lo, cognitive_level=CognitiveLevel.UNDERSTAND)
    _create_question(db_session, subject, teacher.id, 0.70, "Q_PT1_App", pt1, c1, lo, cognitive_level=CognitiveLevel.APPLY)
    _create_question(db_session, subject, teacher.id, 0.35, "Q_PT2_Und", pt2, c1, lo, cognitive_level=CognitiveLevel.UNDERSTAND)
    _create_question(db_session, subject, teacher.id, 0.65, "Q_PT2_App", pt2, c1, lo, cognitive_level=CognitiveLevel.APPLY)

    service = QuickCheckService(db_session)
    result = service.start_quick_check(student, QuickCheckStartRequest(subject_id=subject.id))

    assert 3 <= result.question_count <= 7
    roles = {q.target_role for q in result.questions}
    assert QuickCheckQuestionRole.UNDERSTANDING in roles
    assert QuickCheckQuestionRole.APPLICATION in roles

    # Verify options and question metadata
    for q in result.questions:
        assert len(q.options) == 2
        assert q.content.startswith("Q_")
        assert q.target_problem_type_id in [pt1.id, pt2.id]


def test_prerequisite_question_selection(db_session: Session) -> None:
    subject, pt1, pt2, c1, c_pre, lo, classroom, teacher, student = (
        _create_curriculum_and_classroom(db_session, "PRE")
    )
    student_profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )

    # Concept C1 depends on C_pre as prerequisite (source=prerequisite, target=dependent)
    relation = ConceptRelation(
        source_concept_id=c_pre.id,
        target_concept_id=c1.id,
        relation_type=RelationType.PREREQUISITE,
    )
    db_session.add(relation)

    # Student has weak mastery on C_pre (< 0.50)
    from datetime import datetime, timezone

    db_session.add(
        StudentConceptMastery(
            student_id=student_profile.id,
            concept_id=c_pre.id,
            mastery_score=0.30,
            confidence=0.8,
            attempt_count=3,
            correct_count=1,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )

    # Active plan with PT1
    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=teacher.id,
        items=[TeachingPlanItem(problem_type_id=pt1.id, priority=1, order_index=0)],
    )
    db_session.add(plan)
    db_session.commit()

    # Questions for PT1
    _create_question(db_session, subject, teacher.id, 0.30, "Q_PT1_Und", pt1, c1, lo)
    _create_question(db_session, subject, teacher.id, 0.70, "Q_PT1_App", pt1, c1, lo)
    # Question for prerequisite concept C_pre
    _create_question(db_session, subject, teacher.id, 0.40, "Q_Pre", pt1, c_pre, lo)

    service = QuickCheckService(db_session)
    result = service.start_quick_check(student, QuickCheckStartRequest(subject_id=subject.id))

    prereq_questions = [
        q for q in result.questions if q.target_role == QuickCheckQuestionRole.PREREQUISITE
    ]
    assert len(prereq_questions) == 1
    assert prereq_questions[0].target_concept_id == c_pre.id


def test_mastery_update_on_answer(db_session: Session) -> None:
    subject, pt1, pt2, c1, c_pre, lo, classroom, teacher, student = (
        _create_curriculum_and_classroom(db_session, "MAS")
    )
    student_profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )

    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=teacher.id,
        items=[
            TeachingPlanItem(problem_type_id=pt1.id, priority=1, order_index=0),
            TeachingPlanItem(problem_type_id=pt2.id, priority=1, order_index=1),
        ],
    )
    db_session.add(plan)
    db_session.commit()

    q1 = _create_question(db_session, subject, teacher.id, 0.30, "Q1", pt1, c1, lo, correct_answer="A")
    q2 = _create_question(db_session, subject, teacher.id, 0.60, "Q2", pt1, c1, lo, correct_answer="B")
    q3 = _create_question(db_session, subject, teacher.id, 0.40, "Q3", pt2, c1, lo, correct_answer="A")

    service = QuickCheckService(db_session)
    started = service.start_quick_check(student, QuickCheckStartRequest(subject_id=subject.id))

    # Answer first question correctly
    first_q_id = started.questions[0].question_id
    attempt = service.answer_question(
        student,
        started.id,
        PracticeAnswerCreate(question_id=first_q_id, student_answer="A"),
    )
    assert attempt.is_correct is True

    # Verify mastery update
    pt_mastery = db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == student_profile.id,
            StudentProblemTypeMastery.problem_type_id == pt1.id,
        )
    )
    assert pt_mastery is not None
    assert pt_mastery.attempt_count >= 1

    c_mastery = db_session.scalar(
        select(StudentConceptMastery).where(
            StudentConceptMastery.student_id == student_profile.id,
            StudentConceptMastery.concept_id == c1.id,
        )
    )
    assert c_mastery is not None
    assert c_mastery.attempt_count >= 1


def test_deterministic_result_calculation(db_session: Session) -> None:
    subject, pt1, pt2, c1, c_pre, lo, classroom, teacher, student = (
        _create_curriculum_and_classroom(db_session, "DET")
    )

    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=teacher.id,
        items=[
            TeachingPlanItem(problem_type_id=pt1.id, priority=2, order_index=0),  # Core (priority 2)
            TeachingPlanItem(problem_type_id=pt2.id, priority=1, order_index=1),  # Secondary
        ],
    )
    db_session.add(plan)
    db_session.commit()

    q1 = _create_question(db_session, subject, teacher.id, 0.30, "Q1", pt1, c1, lo, correct_answer="A")
    q2 = _create_question(db_session, subject, teacher.id, 0.60, "Q2", pt1, c1, lo, correct_answer="A")
    q3 = _create_question(db_session, subject, teacher.id, 0.40, "Q3", pt2, c1, lo, correct_answer="A")

    service = QuickCheckService(db_session)
    started = service.start_quick_check(student, QuickCheckStartRequest(subject_id=subject.id))

    # Case A: Answer all correctly -> UNDERSTOOD
    for q in started.questions:
        service.answer_question(
            student,
            started.id,
            PracticeAnswerCreate(question_id=q.question_id, student_answer="A"),
        )

    result = service.get_result(student, started.id)
    assert result.status == PracticeSessionStatus.COMPLETED
    assert result.verdict == QuickCheckVerdict.UNDERSTOOD
    assert result.score == 1.0
    assert result.correct_questions == len(started.questions)

    # Verify problem_type_results
    pt_map = {item.problem_type_id: item for item in result.problem_type_results}
    assert pt1.id in pt_map
    assert pt_map[pt1.id].is_core is True
    assert pt_map[pt1.id].status == QuickCheckVerdict.UNDERSTOOD

    # Verify concept_signals
    assert len(result.concept_signals) >= 1
    assert result.concept_signals[0].signal == ConceptSignalLevel.STRONG


def test_deterministic_weak_verdict_when_core_fails(db_session: Session) -> None:
    subject, pt1, pt2, c1, c_pre, lo, classroom, teacher, student = (
        _create_curriculum_and_classroom(db_session, "WEAK")
    )

    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=teacher.id,
        items=[
            TeachingPlanItem(problem_type_id=pt1.id, priority=3, order_index=0),  # Core (priority 3)
            TeachingPlanItem(problem_type_id=pt2.id, priority=1, order_index=1),  # Secondary
        ],
    )
    db_session.add(plan)
    db_session.commit()

    q1 = _create_question(db_session, subject, teacher.id, 0.30, "Q1", pt1, c1, lo, correct_answer="A")
    q2 = _create_question(db_session, subject, teacher.id, 0.60, "Q2", pt1, c1, lo, correct_answer="A")
    q3 = _create_question(db_session, subject, teacher.id, 0.40, "Q3", pt2, c1, lo, correct_answer="A")

    service = QuickCheckService(db_session)
    started = service.start_quick_check(student, QuickCheckStartRequest(subject_id=subject.id))

    # Student answers core PT1 questions wrong ("B"), and secondary PT2 question right ("A")
    for q in started.questions:
        ans = "B" if q.target_problem_type_id == pt1.id else "A"
        service.answer_question(
            student,
            started.id,
            PracticeAnswerCreate(question_id=q.question_id, student_answer=ans),
        )

    result = service.get_result(student, started.id)
    # Core PT1 failed -> overall verdict must be WEAK even if some other questions were correct
    assert result.verdict == QuickCheckVerdict.WEAK
    pt_map = {item.problem_type_id: item for item in result.problem_type_results}
    assert pt_map[pt1.id].is_core is True
    assert pt_map[pt1.id].status == QuickCheckVerdict.WEAK


def test_empty_plan_and_ineligible_questions(db_session: Session) -> None:
    subject, pt1, pt2, c1, c_pre, lo, classroom, teacher, student = (
        _create_curriculum_and_classroom(db_session, "EDG")
    )
    service = QuickCheckService(db_session)

    # 1. Active plan with no items -> 422 EMPTY_TEACHING_PLAN
    plan_empty = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=teacher.id,
        items=[],
    )
    db_session.add(plan_empty)
    db_session.commit()

    with pytest.raises(ApplicationError) as exc_info:
        service.start_quick_check(student, QuickCheckStartRequest(subject_id=subject.id))
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "EMPTY_TEACHING_PLAN"

    # Fix plan with items
    plan_empty.items = [TeachingPlanItem(problem_type_id=pt1.id, priority=1, order_index=0)]
    db_session.commit()

    _create_question(db_session, subject, teacher.id, 0.30, "Q1", pt1, c1, lo)
    _create_question(db_session, subject, teacher.id, 0.70, "Q2", pt1, c1, lo)
    _create_question(db_session, subject, teacher.id, 0.50, "Q3", pt1, c1, lo)
    unrelated_q = _create_question(db_session, subject, teacher.id, 0.50, "Unrelated", pt2, c1, lo)

    started = service.start_quick_check(student, QuickCheckStartRequest(subject_id=subject.id))

    # Answering an unrelated question not part of the quick check -> 422 QUESTION_NOT_ELIGIBLE
    with pytest.raises(ApplicationError) as exc_info:
        service.answer_question(
            student,
            started.id,
            PracticeAnswerCreate(question_id=unrelated_q.id, student_answer="A"),
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "QUESTION_NOT_ELIGIBLE"


def test_quick_check_api_workflow_and_permissions(
    db_client: TestClient, db_session: Session, settings: Settings
) -> None:
    subject, pt1, pt2, c1, c_pre, lo, classroom, teacher, student = (
        _create_curriculum_and_classroom(db_session, "API")
    )
    teacher_headers = _auth_headers(db_session, settings, teacher)
    student_headers = _auth_headers(db_session, settings, student)

    other_student = _create_user(db_session, Role.STUDENT, "other.student@example.com")
    other_student_headers = _auth_headers(db_session, settings, other_student)

    unassigned_teacher = _create_user(db_session, Role.TEACHER, "unassigned.teacher@example.com")
    unassigned_teacher_headers = _auth_headers(db_session, settings, unassigned_teacher)

    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=teacher.id,
        items=[
            TeachingPlanItem(problem_type_id=pt1.id, priority=1, order_index=0),
            TeachingPlanItem(problem_type_id=pt2.id, priority=1, order_index=1),
        ],
    )
    db_session.add(plan)
    db_session.commit()

    q1 = _create_question(db_session, subject, teacher.id, 0.30, "Q1", pt1, c1, lo, correct_answer="A")
    q2 = _create_question(db_session, subject, teacher.id, 0.70, "Q2", pt1, c1, lo, correct_answer="A")
    q3 = _create_question(db_session, subject, teacher.id, 0.40, "Q3", pt2, c1, lo, correct_answer="A")

    # 1. Unauthenticated -> 401
    assert db_client.post("/learning/quick-check/start", json={"subject_id": str(subject.id)}).status_code == 401

    # 2. Teacher cannot start quick check -> 403
    assert db_client.post(
        "/learning/quick-check/start",
        json={"subject_id": str(subject.id)},
        headers=teacher_headers,
    ).status_code == 403

    # 3. Student starts quick check -> 201
    start_resp = db_client.post(
        "/learning/quick-check/start",
        json={"subject_id": str(subject.id), "classroom_id": str(classroom.id)},
        headers=student_headers,
    )
    assert start_resp.status_code == 201
    session_data = start_resp.json()
    qc_id = session_data["id"]
    assert session_data["question_count"] >= 3
    assert len(session_data["questions"]) >= 3

    # 4. Student answers first question -> 201
    first_q = session_data["questions"][0]
    ans_resp = db_client.post(
        f"/learning/quick-check/{qc_id}/answer",
        json={"question_id": first_q["question_id"], "student_answer": "A"},
        headers=student_headers,
    )
    assert ans_resp.status_code == 201
    assert ans_resp.json()["is_correct"] is True

    # 5. Duplicate answer to same question -> 409
    dup_resp = db_client.post(
        f"/learning/quick-check/{qc_id}/answer",
        json={"question_id": first_q["question_id"], "student_answer": "A"},
        headers=student_headers,
    )
    assert dup_resp.status_code == 409

    # 6. Student owner views result -> 200 with Cache-Control no-store
    res_resp = db_client.get(
        f"/learning/quick-check/{qc_id}/result",
        headers=student_headers,
    )
    assert res_resp.status_code == 200
    assert res_resp.headers.get("Cache-Control") == "no-store"
    assert "verdict" in res_resp.json()

    # 7. Assigned teacher views result -> 200
    res_teacher = db_client.get(
        f"/learning/quick-check/{qc_id}/result",
        headers=teacher_headers,
    )
    assert res_teacher.status_code == 200

    # 8. Unassigned teacher views result -> 403
    res_unassigned = db_client.get(
        f"/learning/quick-check/{qc_id}/result",
        headers=unassigned_teacher_headers,
    )
    assert res_unassigned.status_code == 403

    # 9. Other student views result -> 403
    res_other_student = db_client.get(
        f"/learning/quick-check/{qc_id}/result",
        headers=other_student_headers,
    )
    assert res_other_student.status_code == 403
