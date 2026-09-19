"""PostgreSQL concurrency coverage for duplicate-safe import confirmation."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.concepts.models import Concept
from app.questions.import_service import QuestionImportService
from app.questions.models import Question
from app.subjects.models import Subject
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService


def test_concurrent_confirm_imports_duplicate_content_once(postgres_engine: Engine) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False, autoflush=False)
    with factory() as session:
        teacher = UserService(session).create_user(UserCreate(
            email="concurrent-import@example.com",
            password="Synthetic-Concurrent-Import-Password-2026!",
            full_name="Concurrent Teacher",
            role=Role.TEACHER,
        ))
        subject = Subject(code="CONCURRENT-MATH", name="Mathematics", grade_level=12)
        session.add(subject)
        session.flush()
        concept = Concept(
            subject_id=subject.id,
            code="CONCURRENT-DERIVATIVE",
            name="Derivative",
            description="Derivative",
            grade_level=12,
            order_index=0,
        )
        session.add(concept)
        session.commit()
        row = {
            "subject_code": subject.code,
            "content": "Concurrent duplicate import question",
            "question_type": "TRUE_FALSE",
            "difficulty": 0.5,
            "correct_answer": "TRUE",
            "source": "TEST",
            "exam_weight": 0.5,
            "concepts": [{"code": concept.code, "weight": 1.0}],
        }
        content = json.dumps([row]).encode()
        service = QuestionImportService(session)
        first = service.preview(teacher, file_name="first.json", content=content)
        second = service.preview(teacher, file_name="second.json", content=content)
        teacher_id = teacher.id
    barrier = Barrier(2)

    def confirm(batch_id) -> tuple[int, int]:
        with factory() as session:
            actor = session.get(User, teacher_id)
            assert actor is not None
            barrier.wait(timeout=10)
            report = QuestionImportService(session).confirm(actor, batch_id).report
            return report.imported, report.duplicate

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(confirm, first.batch_id), pool.submit(confirm, second.batch_id)]
        assert sorted(result.result(timeout=20) for result in results) == [(0, 1), (1, 0)]
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(Question)) == 1
