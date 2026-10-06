from __future__ import annotations

from app.core.exceptions import ApplicationError
from app.exams.models import Exam, ExamStatus
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
