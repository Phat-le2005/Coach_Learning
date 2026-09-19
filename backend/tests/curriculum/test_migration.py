from uuid import UUID, uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, MetaData, Table, inspect, select

from app.curriculum.constants import LEGACY_CURRICULUM_VERSION_ID
from tests.migrations import load_migration


NEW_TABLES = {
    "curricula",
    "curriculum_versions",
    "chapters",
    "topics",
    "problem_types",
    "learning_outcomes",
    "problem_type_concepts",
    "problem_type_learning_outcomes",
    "curriculum_import_history",
    "question_problem_types",
    "question_learning_outcomes",
}


def test_curriculum_revision_downgrade_and_legacy_subject_backfill(
    db_engine: Engine,
) -> None:
    migration = load_migration("0009_curriculum_refactor")
    subject_id = uuid4()
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - NEW_TABLES
            old_subjects = Table("subjects", MetaData(), autoload_with=connection)
            connection.execute(old_subjects.insert().values(
                id=str(subject_id),
                code="LEGACY_TEST",
                name="Legacy Test Subject",
                grade_level=12,
            ))
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before
        subjects = Table("subjects", MetaData(), autoload_with=connection)
        version_id = connection.scalar(
            select(subjects.c.curriculum_version_id).where(subjects.c.id == str(subject_id))
        )
        assert UUID(str(version_id)) == LEGACY_CURRICULUM_VERSION_ID
        question_columns = {
            item["name"] for item in inspect(connection).get_columns("questions")
        }
        assert {"source_year", "cognitive_level"} <= question_columns
        attempt_columns = {
            item["name"] for item in inspect(connection).get_columns("student_attempts")
        }
        assert "problem_type_id" in attempt_columns
