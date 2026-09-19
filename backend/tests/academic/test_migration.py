from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import Engine, MetaData, Table, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.subjects.models import Subject
from app.students.models import StudentProfile
from app.users.models import Role, User
from tests.migrations import load_migration


def test_academic_revision_downgrade_preserves_previous_tables(db_engine: Engine) -> None:
    migration = load_migration("0004_academic_domain")
    user_id, profile_id = uuid4(), uuid4()
    with db_engine.begin() as connection:
        connection.execute(User.__table__.insert().values(
            id=user_id, email="existing@example.com", password_hash="synthetic-migration-test-only",
            full_name="Existing student", role=Role.STUDENT,
        ))
        connection.execute(StudentProfile.__table__.insert().values(id=profile_id, user_id=user_id))
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {"subjects", "concepts", "concept_relations"}
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before
        old_subjects = Table("subjects", MetaData(), autoload_with=connection)
        assert connection.execute(select(old_subjects)).all() == []
        assert connection.execute(select(User.id)).scalars().all() == [user_id]
        assert connection.execute(select(StudentProfile.id)).scalars().all() == [profile_id]


@pytest.mark.parametrize("kind,updates", [
    ("subject", {"code": "lowercase"}), ("subject", {"code": " "}), ("subject", {"name": " "}),
    ("subject", {"grade_level": 13}), ("subject", {"description": " "}),
    ("concept", {"subject_id": uuid4()}), ("concept", {"code": "lowercase"}), ("concept", {"name": " "}),
    ("concept", {"description": " "}), ("concept", {"grade_level": 0}), ("concept", {"order_index": -1}),
    ("relation", {"source_concept_id": uuid4()}), ("relation", {"target_concept_id": uuid4()}),
    ("relation", {"relation_type": "INVALID"}),
])
def test_database_enforces_academic_constraints(db_session: Session, kind: str, updates: dict[str, object]) -> None:
    subject = Subject(code="S", name="Subject")
    db_session.add(subject)
    db_session.flush()
    a, b = [Concept(subject_id=subject.id, code=code, name=code, description="Description", grade_level=12, order_index=0) for code in ["A", "B"]]
    db_session.add_all([a, b])
    db_session.commit()
    if kind == "subject":
        entity = Subject(**{"code": "NEW", "name": "New subject", **updates})
    elif kind == "concept":
        entity = Concept(**{"subject_id": subject.id, "code": "NEW", "name": "New", "description": "Description", "grade_level": 12, "order_index": 0, **updates})
    else:
        entity = ConceptRelation(**{"source_concept_id": a.id, "target_concept_id": b.id, "relation_type": RelationType.PREREQUISITE, **updates})
    db_session.add(entity)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_rejects_duplicate_and_self_edges_and_reversed_related_edges(db_session: Session) -> None:
    subject = Subject(code="S", name="Subject")
    db_session.add(subject)
    db_session.flush()
    nodes = [Concept(subject_id=subject.id, code=code, name=code, description="Description", grade_level=12, order_index=0) for code in ["A", "B"]]
    db_session.add_all(nodes)
    db_session.flush()
    a, b = sorted([node.id for node in nodes])
    db_session.add(ConceptRelation(source_concept_id=a, target_concept_id=b, relation_type=RelationType.PREREQUISITE))
    db_session.commit()
    for source, target, kind in [(a, b, RelationType.PREREQUISITE), (a, a, RelationType.PART_OF), (b, a, RelationType.RELATED_TO)]:
        db_session.add(ConceptRelation(source_concept_id=source, target_concept_id=target, relation_type=kind))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
