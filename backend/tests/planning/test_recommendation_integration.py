from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.curriculum.models import (
    Chapter,
    LearningOutcome,
    ProblemType,
    ProblemTypeConcept,
    Topic,
)
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
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
from app.recommendations.priority_service import LearningPriorityService
from app.recommendations.question_service import QuestionRecommendationService
from app.recommendations.schemas import PriorityReasonCode, PriorityTargetType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "Rec-Integration-Test-2026!"


def _create_user(session: Session, role: Role, email: str) -> User:
    return UserService(session).create_user(
        UserCreate(email=email, password=TEST_PASSWORD, full_name="Rec User", role=role)
    )


def _setup_environment(session: Session) -> dict[str, object]:
    teacher_user = _create_user(session, Role.TEACHER, "teacher.rec@example.com")
    student_user = _create_user(session, Role.STUDENT, "student.rec@example.com")

    teacher = session.scalar(select(TeacherProfile).where(TeacherProfile.user_id == teacher_user.id))
    student = session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))

    classroom = Classroom(
        name="12A3",
        academic_year="2025-2026",
        grade_level=12,
        created_by=teacher_user.id,
    )
    classroom.teacher_assignments.append(
        TeacherClassroom(teacher_id=teacher.id, role="OWNER")
    )
    classroom.student_enrollments.append(
        StudentEnrollment(student_id=student.id, status=EnrollmentStatus.ACTIVE)
    )
    session.add(classroom)
    session.flush()

    subject = Subject(code="REC-MATH12", name="Rec Math 12", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code="REC-CHP", name="Chapter", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code="REC-TOP", name="Topic", order_index=0)
    session.add(topic)
    session.flush()

    pt_lesson1 = ProblemType(
        topic_id=topic.id,
        code="PT-LESSON-1",
        name="Current Lesson PT 1",
        order_index=0,
        is_active=True,
    )
    pt_lesson2 = ProblemType(
        topic_id=topic.id,
        code="PT-LESSON-2",
        name="Current Lesson PT 2",
        order_index=1,
        is_active=True,
    )
    pt_other = ProblemType(
        topic_id=topic.id,
        code="PT-OTHER",
        name="Other PT",
        order_index=2,
        is_active=True,
    )
    session.add_all([pt_lesson1, pt_lesson2, pt_other])
    session.flush()

    con_target = Concept(subject_id=subject.id, code="CON-TARGET", name="Target Concept", order_index=0)
    con_prereq = Concept(subject_id=subject.id, code="CON-PREREQ", name="Prereq Concept", order_index=1)
    con_review = Concept(subject_id=subject.id, code="CON-REVIEW", name="Review Concept", order_index=2)
    session.add_all([con_target, con_prereq, con_review])
    session.flush()

    session.add(
        ProblemTypeConcept(
            problem_type_id=pt_lesson1.id,
            concept_id=con_target.id,
            weight=1.0,
            is_primary=True,
        )
    )
    session.add(
        ProblemTypeConcept(
            problem_type_id=pt_other.id,
            concept_id=con_review.id,
            weight=1.0,
            is_primary=True,
        )
    )
    session.add(
        ConceptRelation(
            source_concept_id=con_prereq.id,
            target_concept_id=con_target.id,
            relation_type=RelationType.PREREQUISITE,
        )
    )

    lo = LearningOutcome(
        subject_id=subject.id,
        code="REC-LO",
        description="Outcome",
        grade_level=12,
        order_index=0,
    )
    session.add(lo)
    session.flush()

    q_lesson = Question(
        subject_id=subject.id,
        content="Lesson Question Content",
        question_type=QuestionType.MULTIPLE_CHOICE,
        cognitive_level=CognitiveLevel.APPLY,
        difficulty=0.5,
        source_type="TEST",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        created_by=teacher_user.id,
    )
    q_lesson.options.extend(
        [
            QuestionOption(label="A", content="Opt A", order_index=0),
            QuestionOption(label="B", content="Opt B", order_index=1),
        ]
    )
    session.add(q_lesson)
    session.flush()

    session.add(QuestionProblemType(question_id=q_lesson.id, problem_type_id=pt_lesson1.id, weight=1.0))
    session.add(QuestionConcept(question_id=q_lesson.id, concept_id=con_target.id, weight=1.0))
    session.add(QuestionLearningOutcome(question_id=q_lesson.id, learning_outcome_id=lo.id, weight=1.0))

    session.commit()

    return {
        "teacher": teacher_user,
        "student": student_user,
        "student_profile": student,
        "classroom": classroom,
        "subject": subject,
        "pt_lesson1": pt_lesson1,
        "pt_lesson2": pt_lesson2,
        "pt_other": pt_other,
        "con_target": con_target,
        "con_prereq": con_prereq,
        "con_review": con_review,
        "q_lesson": q_lesson,
    }


def test_active_teaching_plan_prioritizes_current_lesson_items(db_session: Session) -> None:
    env = _setup_environment(db_session)
    student: StudentProfile = env["student_profile"]
    subject: Subject = env["subject"]
    classroom: Classroom = env["classroom"]
    pt1: ProblemType = env["pt_lesson1"]
    pt2: ProblemType = env["pt_lesson2"]

    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=env["teacher"].id,
    )
    plan.items.append(TeachingPlanItem(problem_type_id=pt1.id, priority=2, order_index=0))
    plan.items.append(TeachingPlanItem(problem_type_id=pt2.id, priority=1, order_index=1))
    db_session.add(plan)

    db_session.add(
        StudentConceptMastery(
            student_id=student.id,
            concept_id=env["con_prereq"].id,
            mastery_score=0.9,
            confidence=0.85,
            attempt_count=10,
            correct_count=9,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    priorities = LearningPriorityService(db_session).get_priorities(student.id, subject.id)
    assert len(priorities) > 0

    pt1_priority = next(p for p in priorities if p.problem_type_id == pt1.id)
    pt2_priority = next(p for p in priorities if p.problem_type_id == pt2.id)

    assert pt1_priority.reason_code == PriorityReasonCode.CURRENT_LESSON
    assert pt2_priority.reason_code == PriorityReasonCode.CURRENT_LESSON

    assert pt1_priority.priority_score > pt2_priority.priority_score

    rec = QuestionRecommendationService(db_session).recommend(student.id, subject.id)
    assert rec is not None
    assert rec.reason_code == PriorityReasonCode.CURRENT_LESSON


def test_prerequisite_repair_still_outranks_current_lesson(db_session: Session) -> None:
    env = _setup_environment(db_session)
    student: StudentProfile = env["student_profile"]
    subject: Subject = env["subject"]
    classroom: Classroom = env["classroom"]
    pt1: ProblemType = env["pt_lesson1"]
    con_prereq: Concept = env["con_prereq"]

    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=env["teacher"].id,
    )
    plan.items.append(TeachingPlanItem(problem_type_id=pt1.id, priority=1))
    db_session.add(plan)

    db_session.add(
        StudentConceptMastery(
            student_id=student.id,
            concept_id=con_prereq.id,
            mastery_score=0.2,
            confidence=0.8,
            attempt_count=5,
            correct_count=1,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    priorities = LearningPriorityService(db_session).get_priorities(student.id, subject.id)

    top_priority = priorities[0]
    assert top_priority.target_type == PriorityTargetType.CONCEPT
    assert top_priority.concept_id == con_prereq.id
    assert top_priority.reason_code == PriorityReasonCode.PREREQUISITE_REPAIR

    lesson_priority = next(p for p in priorities if p.problem_type_id == pt1.id)
    assert lesson_priority.reason_code == PriorityReasonCode.CURRENT_LESSON
    assert top_priority.priority_score > lesson_priority.priority_score


def test_review_due_is_supported_alongside_active_teaching_plan(db_session: Session) -> None:
    env = _setup_environment(db_session)
    student: StudentProfile = env["student_profile"]
    subject: Subject = env["subject"]
    classroom: Classroom = env["classroom"]
    pt1: ProblemType = env["pt_lesson1"]
    pt_other: ProblemType = env["pt_other"]

    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=env["teacher"].id,
    )
    plan.items.append(TeachingPlanItem(problem_type_id=pt1.id, priority=1))
    db_session.add(plan)

    db_session.add(
        StudentProblemTypeMastery(
            student_id=student.id,
            problem_type_id=pt_other.id,
            mastery_score=0.85,
            confidence=0.8,
            attempt_count=15,
            correct_count=13,
            last_practiced_at=datetime.now(timezone.utc) - timedelta(days=90),
        )
    )
    db_session.commit()

    priorities = LearningPriorityService(db_session).get_priorities(student.id, subject.id)

    review_item = next((p for p in priorities if p.problem_type_id == pt_other.id), None)
    assert review_item is not None
    assert review_item.reason_code == PriorityReasonCode.REVIEW_DUE


def test_inactive_plan_does_not_trigger_current_lesson(db_session: Session) -> None:
    env = _setup_environment(db_session)
    student: StudentProfile = env["student_profile"]
    subject: Subject = env["subject"]
    classroom: Classroom = env["classroom"]
    pt1: ProblemType = env["pt_lesson1"]

    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.PLANNED,
        created_by=env["teacher"].id,
    )
    plan.items.append(TeachingPlanItem(problem_type_id=pt1.id, priority=1))
    db_session.add(plan)
    db_session.commit()

    priorities = LearningPriorityService(db_session).get_priorities(student.id, subject.id)
    pt1_priority = next(p for p in priorities if p.problem_type_id == pt1.id)
    assert pt1_priority.reason_code != PriorityReasonCode.CURRENT_LESSON
