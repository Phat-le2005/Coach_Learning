from sqlalchemy import Select, select

from app.attempts.models import StudentAttempt
from app.students.models import StudentProfile


def real_attempts_query() -> Select[tuple[StudentAttempt]]:
    """Canonical production analytics scope; synthetic facts are excluded."""
    return (
        select(StudentAttempt)
        .join(StudentProfile, StudentProfile.id == StudentAttempt.student_id)
        .where(
            StudentProfile.is_synthetic.is_(False),
            StudentAttempt.is_synthetic.is_(False),
        )
    )
