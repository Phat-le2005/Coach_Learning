import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.classes.schemas import (
    ClassroomCreate,
    ClassroomRead,
    ClassroomStudentRead,
    StudentClassroomRead,
    StudentEnrollmentCreate,
    TeacherClassroomRead,
)
from app.core.exceptions import ApplicationError
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import User

logger = logging.getLogger(__name__)


class ClassroomService:
    CREATOR_ROLE = "OWNER"

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_for_teacher(self, user_id: UUID, data: ClassroomCreate) -> TeacherClassroomRead:
        teacher = self._teacher_for_user(user_id)
        classroom = Classroom(**data.model_dump(), created_by=user_id)
        classroom.teacher_assignments.append(TeacherClassroom(teacher_id=teacher.id, role=self.CREATOR_ROLE))
        self.session.add(classroom)
        self.session.commit()
        self.session.refresh(classroom)
        logger.info("Classroom created (classroom_id=%s, teacher_id=%s)", classroom.id, teacher.id)
        return self._teacher_view(classroom, self.CREATOR_ROLE)

    def list_for_teacher(self, user_id: UUID) -> list[TeacherClassroomRead]:
        teacher = self._teacher_for_user(user_id)
        rows = self.session.execute(
            select(Classroom, TeacherClassroom.role)
            .join(TeacherClassroom, TeacherClassroom.classroom_id == Classroom.id)
            .where(TeacherClassroom.teacher_id == teacher.id)
            .order_by(Classroom.created_at.desc(), Classroom.name, Classroom.id)
        ).all()
        return [self._teacher_view(classroom, role) for classroom, role in rows]

    def get_for_teacher(self, user_id: UUID, classroom_id: UUID) -> TeacherClassroomRead:
        teacher = self._teacher_for_user(user_id)
        classroom = self._classroom_or_404(classroom_id)
        assignment = self.session.scalar(
            select(TeacherClassroom).where(
                TeacherClassroom.teacher_id == teacher.id,
                TeacherClassroom.classroom_id == classroom_id,
            )
        )
        if assignment is None:
            raise self._access_denied()
        return self._teacher_view(classroom, assignment.role)

    def list_students_for_teacher(self, user_id: UUID, classroom_id: UUID) -> list[ClassroomStudentRead]:
        self.get_for_teacher(user_id, classroom_id)
        rows = self.session.execute(
            select(StudentProfile, User, StudentEnrollment)
            .join(StudentEnrollment, StudentEnrollment.student_id == StudentProfile.id)
            .join(User, User.id == StudentProfile.user_id)
            .where(StudentEnrollment.classroom_id == classroom_id)
            .order_by(User.full_name, User.email, StudentProfile.id)
        ).all()
        return [
            ClassroomStudentRead(
                student_id=profile.id,
                user_id=profile.user_id,
                email=user.email,
                full_name=user.full_name,
                grade_level=profile.grade_level,
                school_name=profile.school_name,
                date_of_birth=profile.date_of_birth,
                is_synthetic=profile.is_synthetic,
                synthetic_profile=profile.synthetic_profile,
                status=enrollment.status,
                joined_at=enrollment.joined_at,
            )
            for profile, user, enrollment in rows
        ]

    def enroll_student(
        self, user_id: UUID, classroom_id: UUID, data: StudentEnrollmentCreate
    ) -> ClassroomStudentRead:
        self.get_for_teacher(user_id, classroom_id)
        profile = self.session.get(StudentProfile, data.student_id)
        if profile is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile was not found.")
        if self._enrollment_exists(data.student_id, classroom_id):
            raise self._already_enrolled()
        enrollment = StudentEnrollment(
            student_id=data.student_id,
            classroom_id=classroom_id,
            status=data.status,
        )
        self.session.add(enrollment)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            if self._enrollment_exists(data.student_id, classroom_id):
                raise self._already_enrolled() from None
            self._classroom_or_404(classroom_id)
            if self.session.get(StudentProfile, data.student_id) is None:
                raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile was not found.") from None
            raise
        self.session.refresh(enrollment)
        user = self.session.get(User, profile.user_id)
        if user is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile was not found.")
        logger.info(
            "Student enrolled (classroom_id=%s, student_id=%s, status=%s)",
            classroom_id,
            profile.id,
            enrollment.status.value,
        )
        return ClassroomStudentRead(
            student_id=profile.id,
            user_id=profile.user_id,
            email=user.email,
            full_name=user.full_name,
            grade_level=profile.grade_level,
            school_name=profile.school_name,
            date_of_birth=profile.date_of_birth,
            is_synthetic=profile.is_synthetic,
            synthetic_profile=profile.synthetic_profile,
            status=enrollment.status,
            joined_at=enrollment.joined_at,
        )

    def list_for_student(self, user_id: UUID) -> list[StudentClassroomRead]:
        student = self._student_for_user(user_id)
        rows = self.session.execute(
            select(Classroom, StudentEnrollment)
            .join(StudentEnrollment, StudentEnrollment.classroom_id == Classroom.id)
            .where(StudentEnrollment.student_id == student.id)
            .order_by(Classroom.created_at.desc(), Classroom.name, Classroom.id)
        ).all()
        return [self._student_view(classroom, enrollment) for classroom, enrollment in rows]

    def _teacher_for_user(self, user_id: UUID) -> TeacherProfile:
        teacher = self.session.scalar(select(TeacherProfile).where(TeacherProfile.user_id == user_id))
        if teacher is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Teacher profile was not found.")
        return teacher

    def _student_for_user(self, user_id: UUID) -> StudentProfile:
        student = self.session.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))
        if student is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
        return student

    def _classroom_or_404(self, classroom_id: UUID) -> Classroom:
        classroom = self.session.get(Classroom, classroom_id)
        if classroom is None:
            raise ApplicationError(404, "CLASSROOM_NOT_FOUND", "Classroom was not found.")
        return classroom

    def _enrollment_exists(self, student_id: UUID, classroom_id: UUID) -> bool:
        return self.session.scalar(
            select(StudentEnrollment.student_id).where(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.classroom_id == classroom_id,
            )
        ) is not None

    @staticmethod
    def _access_denied() -> ApplicationError:
        return ApplicationError(403, "CLASSROOM_ACCESS_DENIED", "You are not assigned to this classroom.")

    @staticmethod
    def _already_enrolled() -> ApplicationError:
        return ApplicationError(409, "STUDENT_ALREADY_ENROLLED", "Student is already enrolled in this classroom.")

    @staticmethod
    def _teacher_view(classroom: Classroom, role: str) -> TeacherClassroomRead:
        data = ClassroomRead.model_validate(classroom).model_dump()
        return TeacherClassroomRead(**data, teacher_role=role)

    @staticmethod
    def _student_view(classroom: Classroom, enrollment: StudentEnrollment) -> StudentClassroomRead:
        data = ClassroomRead.model_validate(classroom).model_dump()
        return StudentClassroomRead(
            **data,
            enrollment_status=enrollment.status,
            joined_at=enrollment.joined_at,
        )
