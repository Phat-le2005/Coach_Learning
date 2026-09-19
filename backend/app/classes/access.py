from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.models import EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.core.exceptions import ApplicationError
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile


@dataclass(frozen=True, slots=True)
class TeacherStudentRelationship:
    teacher: TeacherProfile
    student: StudentProfile


class TeacherStudentAccessService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def require_active_relationship(
        self,
        teacher_user_id: UUID,
        student_id: UUID,
        *,
        denied_code: str = "STUDENT_ACCESS_DENIED",
    ) -> TeacherStudentRelationship:
        teacher = self.session.scalar(
            select(TeacherProfile).where(TeacherProfile.user_id == teacher_user_id)
        )
        if teacher is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Teacher profile was not found.")
        student = self.session.get(StudentProfile, student_id)
        if student is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile was not found.")
        relationship = self.session.scalar(
            select(TeacherClassroom.teacher_id)
            .join(
                StudentEnrollment,
                StudentEnrollment.classroom_id == TeacherClassroom.classroom_id,
            )
            .where(
                TeacherClassroom.teacher_id == teacher.id,
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
            )
            .limit(1)
        )
        if relationship is None:
            raise ApplicationError(
                403,
                denied_code,
                "Teacher does not have an active classroom relationship with this student.",
            )
        return TeacherStudentRelationship(teacher=teacher, student=student)
