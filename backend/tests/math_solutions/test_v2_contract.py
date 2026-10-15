from app.api.export_contract import get_deterministic_schema
from app.api.v2.check_contract import check_v2_contract
from app.api.v2.export_contract import get_v2_deterministic_schema


EXPECTED_PATHS = {
    "/math-solutions/attempts",
    "/math-solutions/attempts/{attempt_id}/ink",
    "/math-solutions/attempts/{attempt_id}/ink/pages/{page_index}",
    "/math-solutions/attempts/{attempt_id}",
    "/math-solutions/attempts/{attempt_id}/problem",
    "/math-solutions/attempts/{attempt_id}/steps",
    "/math-solutions/attempts/{attempt_id}/steps/{step_id}",
    "/math-solutions/attempts/{attempt_id}/steps/{step_id}/delete",
    "/math-solutions/attempts/{attempt_id}/steps/{step_id}/restore",
    "/math-solutions/attempts/{attempt_id}/reorder",
    "/math-solutions/attempts/{attempt_id}/steps/{step_id}/revisions",
    "/math-solutions/attempts/{attempt_id}/steps/{step_id}/rollback",
    "/math-solutions/attempts/{attempt_id}/submit",
    "/math-solutions/practice-sessions/{session_id}/next-problem",
    "/math-solutions/student-assignments/{student_assignment_id}/prepare",
    "/math-solutions/student-assignments/{student_assignment_id}/problems",
}


def test_v2_contract_is_isolated_and_complete() -> None:
    v1 = get_deterministic_schema()
    v2 = get_v2_deterministic_schema()
    assert set(v2["paths"]) == EXPECTED_PATHS
    assert EXPECTED_PATHS.isdisjoint(v1["paths"])
    assert all(not path.startswith("/api/v2") for path in v2["paths"])
    assert v2["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"


def test_v2_response_contract_does_not_expose_protected_answer_or_rubric() -> None:
    schema = get_v2_deterministic_schema()
    response_properties = schema["components"]["schemas"]["SolutionAttemptRead"]["properties"]
    assert "correct_answer" not in response_properties
    assert "explanation" not in response_properties
    assert "rubric_id" not in response_properties
    assert "student_id" not in response_properties

    problem_properties = schema["components"]["schemas"]["ProblemRead"]["properties"]
    assert "correct_answer" not in problem_properties
    assert "explanation" not in problem_properties
    assert "rubric" not in problem_properties
    assert "storage_key" not in problem_properties

    option_properties = schema["components"]["schemas"]["ProblemOptionRead"]["properties"]
    assert "is_correct" not in option_properties


def test_v2_contract_snapshot_is_current() -> None:
    assert check_v2_contract() == 0