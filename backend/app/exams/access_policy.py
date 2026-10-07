from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.core.exceptions import ApplicationError
from app.exams.models import Exam, ExamAttempt, ExamStatus
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile
from app.users.models import Role, User


def assert_exam_access(user: User, exam: Exam) -> None:
    """Authorize access to an Exam model instance according to user role.

    - Admin: full access to all exams.
    - Teacher: can only access exams created by themselves (403 if created by another user).
    - Student: can only access PUBLISHED exams (404 EXAM_NOT_FOUND if draft/archived).
    """
    if user.role == Role.ADMIN:
        return
    if user.role == Role.TEACHER:
        if exam.created_by != user.id:
            raise ApplicationError(403, "EXAM_ACCESS_DENIED", "Access denied to exam.")
        return
    if user.role == Role.STUDENT:
        if exam.status != ExamStatus.PUBLISHED:
            raise ApplicationError(404, "EXAM_NOT_FOUND", "Exam not found.")
        return
    raise ApplicationError(403, "ACCESS_DENIED", "Unauthorized role for exam access.")


def assert_exam_attempt_access(
    session: Session,
    user: User,
    attempt: ExamAttempt,
) -> None:
    """Authorize access to an ExamAttempt model instance according to user role.

    - Admin: full access to any attempt.
    - Student: can only access their own attempt (404 ATTEMPT_NOT_FOUND if other student or missing profile).
    - Teacher: can only access attempt if the student is ACTIVELY enrolled in a classroom
      that the teacher is assigned to (TeacherClassroom) or owns/created (Classroom.created_by).
      Otherwise 403 EXAM_ATTEMPT_ACCESS_DENIED.
    - Parent: forbidden from generic exam attempt endpoints (403 EXAM_ATTEMPT_ACCESS_DENIED).
    - Unknown role: fallback 403 EXAM_ATTEMPT_ACCESS_DENIED.
    """
    if user.role == Role.ADMIN:
        return

    if user.role == Role.STUDENT:
        student_prof = session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user.id)
        )
        if student_prof is None or student_prof.id != attempt.student_id:
            raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Exam attempt not found.")
        return

    if user.role == Role.TEACHER:
        teacher_prof = session.scalar(
            select(TeacherProfile).where(TeacherProfile.user_id == user.id)
        )
        if teacher_prof is None:
            raise ApplicationError(
                403,
                "EXAM_ATTEMPT_ACCESS_DENIED",
                "Teacher does not have permission to view this student's exam attempt.",
            )

        has_classroom_access = session.scalar(
            select(StudentEnrollment.classroom_id)
            .join(Classroom, StudentEnrollment.classroom_id == Classroom.id)
            .outerjoin(TeacherClassroom, Classroom.id == TeacherClassroom.classroom_id)
            .where(
                StudentEnrollment.student_id == attempt.student_id,
                StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                or_(
                    TeacherClassroom.teacher_id == teacher_prof.id,
                    Classroom.created_by == user.id,
                ),
            )
            .limit(1)
        )
        if has_classroom_access is None:
            raise ApplicationError(
                403,
                "EXAM_ATTEMPT_ACCESS_DENIED",
                "Teacher does not have permission to view this student's exam attempt.",
            )
        return

    if user.role == Role.PARENT:
        raise ApplicationError(
            403,
            "EXAM_ATTEMPT_ACCESS_DENIED",
            "Parents must view student progress via Parent Portal aggregate endpoints.",
        )

    raise ApplicationError(
        403,
        "EXAM_ATTEMPT_ACCESS_DENIED",
        "Unauthorized role for exam attempt access.",
    )

