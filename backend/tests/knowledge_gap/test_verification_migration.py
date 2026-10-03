"""Migration coverage for root-cause verification hardening."""

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect

from tests.migrations import load_migration


def _constraint_names(rows: list[dict[str, object]]) -> set[str]:
    return {str(row["name"]) for row in rows if row.get("name") is not None}


def test_verification_hardening_migration_upgrade_and_downgrade(
    db_engine: Engine,
) -> None:
    migration = load_migration("0036_root_cause_verification_hardening")

    with db_engine.begin() as connection:
        inspector = inspect(connection)
        assert "uq_root_cause_verification_diagnosis" in _constraint_names(
            inspector.get_unique_constraints("root_cause_verifications")
        )
        assert "uq_root_cause_verification_target_question" in _constraint_names(
            inspector.get_unique_constraints("root_cause_verification_items")
        )
        assert (
            "ck_root_cause_verifications_completed_probes_not_exceed_required"
            in _constraint_names(
                inspector.get_check_constraints("root_cause_verifications")
            )
        )
        assert (
            "ck_root_cause_verification_targets_correct_count_not_exceed_probe_count"
            in _constraint_names(
                inspector.get_check_constraints("root_cause_verification_targets")
            )
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

        inspector = inspect(connection)
        assert {
            "root_cause_verifications",
            "root_cause_verification_targets",
            "root_cause_verification_items",
        }.issubset(set(inspector.get_table_names()))
        assert "uq_root_cause_verification_diagnosis" not in _constraint_names(
            inspector.get_unique_constraints("root_cause_verifications")
        )
        practice_checks = inspector.get_check_constraints("practice_sessions")
        assert any(
            "ROOT_CAUSE_VERIFICATION" in str(check.get("sqltext"))
            for check in practice_checks
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

        inspector = inspect(connection)
        assert "uq_root_cause_verification_diagnosis" in _constraint_names(
            inspector.get_unique_constraints("root_cause_verifications")
        )
        assert "uq_root_cause_verification_target_question" in _constraint_names(
            inspector.get_unique_constraints("root_cause_verification_items")
        )
