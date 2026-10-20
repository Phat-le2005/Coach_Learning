from datetime import date

from sqlalchemy.orm import Session

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment
from app.curriculum.models import Chapter, ProblemType, Topic
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.recommendations.priority_service import LearningPriorityService
from app.recommendations.schemas import PriorityReasonCode
from app.student_learning_state.service import StudentLearningStateService
from app.students.models import StudentProfile
from app.subjects.models import Subject
from tests.practice.conftest import PracticeContent


def test_retired_and_other_subject_plan_items_do_not_block_student_home(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    retired = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code="RETIRED_PLAN_TARGET",
        name="Retired plan target",
        description="A previous curriculum target retained in the teacher plan.",
        order_index=21,
        is_active=False,
    )
    other_subject = Subject(code="OTHER_SUBJECT", name="Other subject", grade_level=12)
    db_session.add_all([retired, other_subject])
    db_session.flush()
    other_chapter = Chapter(
        subject_id=other_subject.id,
        code="OTHER_CHAPTER",
        name="Other chapter",
        order_index=0,
    )
    db_session.add(other_chapter)
    db_session.flush()
    other_topic = Topic(
        chapter_id=other_chapter.id,
        code="OTHER_TOPIC",
        name="Other topic",
        order_index=0,
    )
    db_session.add(other_topic)
    db_session.flush()
    other_target = ProblemType(
        topic_id=other_topic.id,
        code="OTHER_SUBJECT_TARGET",
        name="Other subject target",
        order_index=0,
        is_active=True,
    )
    classroom = Classroom(
        name="Retired plan test",
        academic_year="2026-2027",
        grade_level=12,
        created_by=student_profile.user_id,
    )
    db_session.add_all([other_target, classroom])
    db_session.flush()
    db_session.add(
        StudentEnrollment(
            student_id=student_profile.id,
            classroom_id=classroom.id,
            status=EnrollmentStatus.ACTIVE,
        )
    )
    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=practice_content.subject.id,
        start_date=date(2026, 10, 1),
        status=TeachingPlanStatus.ACTIVE,
        created_by=student_profile.user_id,
    )
    db_session.add(plan)
    db_session.flush()
    plan_items = [
        TeachingPlanItem(teaching_plan_id=plan.id, problem_type_id=practice_content.problem_type.id, priority=3),
        TeachingPlanItem(teaching_plan_id=plan.id, problem_type_id=retired.id, priority=2),
        TeachingPlanItem(teaching_plan_id=plan.id, problem_type_id=other_target.id, priority=1),
    ]
    db_session.add_all(plan_items)
    db_session.flush()

    service = LearningPriorityService(db_session)
    resolved = service._resolve_active_teaching_plan(student_profile.id, practice_content.subject.id)
    assert resolved is not None
    assert resolved.problem_type_ids == (practice_content.problem_type.id,)
    assert any(
        priority.problem_type_id == practice_content.problem_type.id
        and priority.reason_code == PriorityReasonCode.CURRENT_LESSON
        for priority in service.get_priorities(student_profile.id, practice_content.subject.id)
    )
    state = StudentLearningStateService(db_session).get_learning_state(
        student_profile.id, subject_id=practice_content.subject.id
    )
    assert state.student_id == student_profile.id
    assert db_session.query(TeachingPlanItem).filter(TeachingPlanItem.teaching_plan_id == plan.id).count() == 3
