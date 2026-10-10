from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.models import Classroom, StudentEnrollment, TeacherClassroom
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.models import PracticeSession
from app.practice.schemas import PracticeAnswerCreate, PracticeSessionCreate
from app.practice.service import PracticeService
from app.students.goal_models import AcademicGoal
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from tests.practice.conftest import PracticeContent

BearerFactory = Callable[[User], dict[str, str]]
UserFactory = Callable[[Role, str], User]


def create_mastery_evidence(
    session: Session, student: User, content: PracticeContent
) -> StudentProfile:
    service = PracticeService(session)
    practice = service.create_session(
        student,
        PracticeSessionCreate(
            subject_id=content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=[content.problem_type.id],
            concept_ids=[content.concept.id],
        ),
    )
    service.answer(
        student,
        practice.id,
        PracticeAnswerCreate(question_id=content.mcq.id, student_answer="B"),
    )
    profile = session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    assert profile is not None
    return profile


def test_new_student_receives_complete_curriculum_without_learning_activity(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    _, student = practice_students
    profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    assert profile is not None
    headers = practice_bearer(student)

    assert db_session.scalar(
        select(StudentEnrollment).where(StudentEnrollment.student_id == profile.id)
    ) is None
    assert db_session.scalar(
        select(AcademicGoal).where(AcademicGoal.student_id == profile.id)
    ) is None
    assert db_session.scalar(
        select(PracticeSession).where(PracticeSession.student_id == profile.id)
    ) is None
    assert db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == profile.id
        )
    ) is None
    assert db_session.scalar(
        select(StudentConceptMastery).where(StudentConceptMastery.student_id == profile.id)
    ) is None

    learning_state = db_client.get("/students/me/learning-state", headers=headers)
    assert learning_state.status_code == 200, learning_state.text
    assert learning_state.json()["available_subjects"] == []
    assert learning_state.json()["class_contexts"] == []
    assert learning_state.json()["today_plan"] is None

    overview = db_client.get("/students/me/mastery", headers=headers)
    assert overview.status_code == 200, overview.text
    subject = next(
        item
        for item in overview.json()["subjects"]
        if item["subject_id"] == str(practice_content.subject.id)
    )
    assert len(subject["chapters"]) == 1
    assert len(subject["chapters"][0]["topics"]) == 1
    leaves = subject["chapters"][0]["topics"][0]["problem_types"]
    assert len(leaves) == 1
    assert leaves[0]["state"] == "NOT_STARTED"
    assert leaves[0]["attempt_count"] == 0
    assert leaves[0]["mastery_score"] == 0.0
    assert subject["concepts"][0]["state"] == "NOT_STARTED"

    # Both read endpoints are side-effect free: the catalog is not fake mastery.
    assert db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == profile.id
        )
    ) is None
    assert db_session.scalar(
        select(StudentConceptMastery).where(StudentConceptMastery.student_id == profile.id)
    ) is None


def test_student_mastery_api_returns_hierarchy_and_leaf_details(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    profile = create_mastery_evidence(db_session, student, practice_content)
    headers = practice_bearer(student)

    overview = db_client.get("/students/me/mastery", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.headers["cache-control"] == "no-store"
    assert overview.json()["student_id"] == str(profile.id)
    subject = next(
        item
        for item in overview.json()["subjects"]
        if item["subject_id"] == str(practice_content.subject.id)
    )
    assert subject["chapters"][0]["topics"][0]["problem_types"][0][
        "attempt_count"
    ] == 1
    assert subject["concepts"][0]["attempt_count"] == 1

    problem = db_client.get(
        f"/students/me/mastery/problem-types/{practice_content.problem_type.id}",
        headers=headers,
    )
    concept = db_client.get(
        f"/students/me/mastery/concepts/{practice_content.concept.id}",
        headers=headers,
    )
    assert problem.status_code == concept.status_code == 200
    assert problem.json()["attempt_count"] == concept.json()["attempt_count"] == 1
    assert problem.json()["state"] == concept.json()["state"] == "LEARNING"


def test_teacher_mastery_api_requires_active_classroom_relationship(
    db_client: TestClient,
    db_session: Session,
    practice_students: tuple[User, User],
    practice_user_factory: UserFactory,
    practice_bearer: BearerFactory,
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    profile = create_mastery_evidence(db_session, student, practice_content)
    teacher = practice_user_factory(Role.TEACHER, "mastery-teacher@example.com")
    unrelated = practice_user_factory(Role.TEACHER, "unrelated-mastery-teacher@example.com")
    teacher_profile = db_session.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == teacher.id)
    )
    assert teacher_profile is not None
    classroom = Classroom(
        name="Mastery Classroom",
        academic_year="2026-2027",
        grade_level=12,
        created_by=teacher.id,
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add_all(
        [
            TeacherClassroom(
                teacher_id=teacher_profile.id,
                classroom_id=classroom.id,
                role="OWNER",
            ),
            StudentEnrollment(student_id=profile.id, classroom_id=classroom.id),
        ]
    )
    db_session.commit()

    allowed = db_client.get(
        f"/teacher/students/{profile.id}/mastery",
        headers=practice_bearer(teacher),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["student_id"] == str(profile.id)

    denied = db_client.get(
        f"/teacher/students/{profile.id}/mastery",
        headers=practice_bearer(unrelated),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "STUDENT_MASTERY_ACCESS_DENIED"
