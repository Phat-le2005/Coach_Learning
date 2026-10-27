"""STEP-ARCH-01 schema smoke tests; database integration runs separately."""
from app.database import models as _all_models  # noqa: F401; resolve foreign keys
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.database.base import Base
from app.math_solutions import models as m


def test_math_solutions_registers_ten_tables():
    names={table for table in Base.metadata.tables if table.startswith("math_") and not table.startswith("math_ink_") and not table.startswith("math_paper_")}
    assert names == {
        "math_solution_rubrics","math_solution_attempts","math_solution_steps",
        "math_step_revisions","math_artifacts","math_step_evaluations",
        "math_solution_feedbacks","math_evaluation_decisions",
        "math_evaluation_overrides","math_solution_operations",
    }


def test_partial_unique_index_compiles_for_postgres():
    table=m.SolutionStep.__table__
    partial=next(i for i in table.indexes if i.name=="uq_math_solution_step_active_index")
    compiled=str(CreateIndex(partial).compile(dialect=postgresql.dialect()))
    assert "WHERE is_deleted = false" in compiled
    assert "DEFERRABLE" not in compiled
    assert "CREATE UNIQUE INDEX" in compiled


def test_schema_can_compile_to_postgresql_without_connections():
    for model in (
        m.SolutionRubric,m.SolutionAttempt,m.SolutionStep,m.StepRevision,
        m.MathArtifact,m.StepEvaluation,m.SolutionFeedback,
        m.EvaluationDecision,m.EvaluationOverride,m.SolutionOperation,
    ):
        ddl=str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
        assert "CREATE TABLE" in ddl
        assert "FOREIGN KEY" in ddl
        assert "CHECK" in ddl or model is m.MathArtifact


def test_no_evidence_mutations_in_models():
    assert not hasattr(m.SolutionStep, "learning_evidence_event_id")
    assert "learning_evidence_event_id" not in m.SolutionOperation.__table__.c
    assert m.EvaluationOverride.__table__.c.projection_status.server_default.arg == "PENDING"


def test_sqlalchemy_identity_and_sources_are_present():
    expected={"question_id","assignment_material_item_id","student_assignment_material_item_id","assignment_student_question_id","student_assignment_id","rubric_id"}
    assert expected.issubset(m.SolutionAttempt.__table__.c.keys())
