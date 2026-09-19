from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.attempts.models import StudentAttempt, StudySession
from app.concepts.models import Concept
from app.core.config import Settings
from app.students.models import StudentProfile, SyntheticProfile
from app.subjects.models import Subject
from app.synthetic_student_service import SyntheticStudentService


def test_postgres_generator_is_idempotent(
    postgres_engine: Engine, settings: Settings
) -> None:
    with Session(postgres_engine, expire_on_commit=False) as session:
        subject = Subject(code="PG_SYNTH_MATH", name="PostgreSQL Synthetic Math", grade_level=12)
        session.add(subject)
        session.flush()
        session.add_all(
            [
                Concept(
                    subject_id=subject.id,
                    code=code,
                    name=name,
                    description=f"PostgreSQL test {name}",
                    grade_level=12,
                    order_index=index,
                )
                for index, (code, name) in enumerate(
                    [("FUNCTION", "Function"), ("OXYZ", "Oxyz")]
                )
            ]
        )
        session.commit()

        first = SyntheticStudentService(session, settings).generate(
            count=2, seed=2026, profile=SyntheticProfile.SPECIFIC_GAP
        )
        second = SyntheticStudentService(session, settings).generate(
            count=2, seed=2026, profile=SyntheticProfile.SPECIFIC_GAP
        )

        assert first.students_created == 2
        assert second.students_created == 0 and second.students_updated == 2
        assert session.scalar(
            select(func.count())
            .select_from(StudentProfile)
            .where(StudentProfile.is_synthetic.is_(True))
        ) == 2
        assert session.scalar(select(func.count()).select_from(StudentAttempt)) == 96
        assert session.scalar(select(func.count()).select_from(StudySession)) == 16
