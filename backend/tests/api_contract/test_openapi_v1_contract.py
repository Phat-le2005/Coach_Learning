import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.api.export_contract import (
    OPENAPI_JSON_PATH,
    OPENAPI_SHA256_PATH,
    compute_compact_sha256,
    get_deterministic_schema,
)
from app.api.version import API_VERSION

FROZEN_CONTRACT_SHA256 = "01b558addf218c6d47a0e22d7ccd04f6d246170e8661b8d5c0fb844ea513e008"


@pytest.fixture(scope="module")
def openapi_schema() -> dict[str, Any]:
    return get_deterministic_schema()


def test_openapi_matches_frozen_contract_and_hash(openapi_schema: dict[str, Any]) -> None:
    assert OPENAPI_JSON_PATH.exists(), f"Missing frozen contract file at {OPENAPI_JSON_PATH}"
    assert OPENAPI_SHA256_PATH.exists(), f"Missing frozen contract hash at {OPENAPI_SHA256_PATH}"

    expected_schema = json.loads(OPENAPI_JSON_PATH.read_text(encoding="utf-8"))
    expected_hash = OPENAPI_SHA256_PATH.read_text(encoding="utf-8").strip()

    assert openapi_schema == expected_schema, "OpenAPI schema differs from frozen openapi-v1.json"
    actual_hash = compute_compact_sha256(openapi_schema)
    assert actual_hash == expected_hash, f"Hash mismatch: expected {expected_hash}, got {actual_hash}"
    assert expected_hash == FROZEN_CONTRACT_SHA256, (
        f"Contract hash changed from baseline! Expected {FROZEN_CONTRACT_SHA256}, got {expected_hash}"
    )
    assert openapi_schema["info"]["version"] == "1.0.0"
    assert API_VERSION == "1.0.0"


def test_contract_generation_ignores_local_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "Totally Different App")
    monkeypatch.setenv("FRONTEND_URL", "http://example.invalid")
    monkeypatch.setenv("DATABASE_NAME", "different_db")
    monkeypatch.setenv("DATABASE_USER", "different_user")
    monkeypatch.setenv("AI_PROVIDER", "some-other-provider")

    isolated_schema = get_deterministic_schema()
    assert isolated_schema["info"]["title"] == "EduMS"
    assert isolated_schema["info"]["version"] == "1.0.0"

    expected_schema = json.loads(OPENAPI_JSON_PATH.read_text(encoding="utf-8"))
    assert isolated_schema == expected_schema
    assert compute_compact_sha256(isolated_schema) == FROZEN_CONTRACT_SHA256


def test_critical_methods_map(openapi_schema: dict[str, Any]) -> None:
    paths = openapi_schema["paths"]

    critical_map = {
        "/auth/login": ["post"],
        "/auth/register": ["post"],
        "/auth/refresh": ["post"],
        "/auth/me": ["get"],
        "/students/me": ["get"],
        "/students/me/goals": ["get", "post"],
        "/students/me/learning-state": ["get"],
        "/students/me/today": ["get"],
        "/students/me/today/explanation": ["post"],
        "/students/me/study-plan": ["get"],
        "/students/me/study-plan/recalculate": ["post"],
        "/parent/students": ["get"],
        "/parent/students/{student_id}/progress": ["get"],
        "/parent/students/{student_id}/weekly-data": ["get"],
        "/parent/students/{student_id}/ai-summary": ["post"],
        "/exams": ["get", "post"],
        "/exams/{exam_id}/start": ["post"],
        "/exams/attempts/{attempt_id}": ["get"],
        "/exams/attempts/{attempt_id}/answer": ["post"],
        "/exams/attempts/{attempt_id}/submit": ["post"],
        "/exams/attempts/{attempt_id}/finalize-timeout": ["post"],
        "/exams/attempts/{attempt_id}/analytics": ["get"],
        "/exams/attempts/{attempt_id}/ai-explanation": ["post"],
        "/teacher-materials/upload": ["post"],
        "/teacher-materials/{material_id}/map": ["post"],
        "/repair/adaptive/{adaptive_session_id}/next-action": ["get", "post"],
        "/teacher/classes/{id}/analytics": ["get"],
        "/teacher/classes/{id}/heatmap": ["get"],
        "/teacher/classes/{id}/alerts": ["get"],
        "/teacher/classes/{id}/students/{student_id}/analytics": ["get"],
        "/teacher/classes/{id}/assignments/{assignment_id}/analytics": ["get"],
        "/teacher/classes/{id}/copilot": ["post"],
    }

    for path, expected_methods in critical_map.items():
        assert path in paths, f"Expected critical path '{path}' not found in OpenAPI"
        path_item = paths[path]
        for method in expected_methods:
            assert method in path_item, f"Expected method '{method.upper()}' missing for path '{path}'"


def test_study_method_invariants(openapi_schema: dict[str, Any]) -> None:
    paths = openapi_schema["paths"]
    assert "get" in paths["/students/me/today"]
    assert "post" not in paths["/students/me/today"]

    assert "post" in paths["/students/me/today/explanation"]
    assert "get" not in paths["/students/me/today/explanation"]

    assert "get" in paths["/students/me/study-plan"]
    assert "post" not in paths["/students/me/study-plan"]

    assert "post" in paths["/students/me/study-plan/recalculate"]
    assert "get" not in paths["/students/me/study-plan/recalculate"]


def test_repair_method_invariants(openapi_schema: dict[str, Any]) -> None:
    paths = openapi_schema["paths"]
    ep = "/repair/adaptive/{adaptive_session_id}/next-action"
    assert ep in paths
    assert "get" in paths[ep]
    assert "post" in paths[ep]
    assert "patch" not in paths[ep]
    assert "delete" not in paths[ep]


def test_teacher_analytics_invariants(openapi_schema: dict[str, Any]) -> None:
    paths = openapi_schema["paths"]
    analytics_paths = {
        "/teacher/classes/{id}/analytics": "get",
        "/teacher/classes/{id}/heatmap": "get",
        "/teacher/classes/{id}/alerts": "get",
        "/teacher/classes/{id}/students/{student_id}/analytics": "get",
        "/teacher/classes/{id}/assignments/{assignment_id}/analytics": "get",
        "/teacher/classes/{id}/copilot": "post",
    }
    for path, method in analytics_paths.items():
        assert path in paths, f"Teacher analytics path '{path}' missing in OpenAPI"
        assert method in paths[path], f"Teacher analytics method '{method.upper()}' missing for '{path}'"


def test_ai_generation_endpoints_strictly_post_no_get(openapi_schema: dict[str, Any]) -> None:
    paths = openapi_schema["paths"]

    ai_generation_endpoints = [
        "/parent/students/{student_id}/ai-summary",
        "/exams/attempts/{attempt_id}/ai-explanation",
        "/students/me/today/explanation",
        "/practice/attempts/{attempt_id}/ai-evaluate",
        "/teacher-materials/{material_id}/map",
        "/students/me/admission-assistant",
    ]

    for ep in ai_generation_endpoints:
        assert ep in paths, f"Endpoint '{ep}' missing from OpenAPI"
        ops = paths[ep]
        assert "post" in ops, f"AI generation endpoint '{ep}' must support POST"
        assert "get" not in ops, f"AI generation endpoint '{ep}' must NOT expose GET for mutation/generation"


def test_no_api_v1_prefix_invariant(openapi_schema: dict[str, Any]) -> None:
    paths = openapi_schema["paths"]
    for path in paths:
        assert not path.startswith("/api/v1"), f"Path '{path}' contains forbidden /api/v1 prefix"


def test_hidden_aliases_absent_from_openapi(openapi_schema: dict[str, Any]) -> None:
    paths = openapi_schema["paths"]
    hidden_aliases = [
        "/parents/students/{student_id}/weekly-data",
        "/parents/students/{student_id}/ai-summary",
    ]
    for alias in hidden_aliases:
        assert alias not in paths, f"Hidden alias path '{alias}' must not be exposed in OpenAPI documentation"


def test_http_bearer_security_scheme_present(openapi_schema: dict[str, Any]) -> None:
    security_schemes = openapi_schema.get("components", {}).get("securitySchemes", {})
    assert "HTTPBearer" in security_schemes, "HTTPBearer security scheme missing"
    assert security_schemes["HTTPBearer"]["type"] == "http"
    assert security_schemes["HTTPBearer"]["scheme"] == "bearer"


def test_sanitized_exam_question_does_not_leak_answers(openapi_schema: dict[str, Any]) -> None:
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    assert "ExamQuestionSanitizedRead" in schemas, "ExamQuestionSanitizedRead schema missing"
    properties = schemas["ExamQuestionSanitizedRead"].get("properties", {})
    assert "correct_answer" not in properties, "Security leak: correct_answer exposed in sanitized exam question"
    assert "explanation" not in properties, "Security leak: explanation exposed in sanitized exam question"


def _extract_boundary(schema: dict[str, Any], *keys: str) -> int | None:
    for k in keys:
        if k in schema and schema[k] is not None:
            return int(schema[k])
    return None


def test_pagination_limits_bounded(openapi_schema: dict[str, Any]) -> None:
    paths = openapi_schema["paths"]
    checked_count = 0

    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            parameters = operation.get("parameters", [])
            for param in parameters:
                if not isinstance(param, dict) or param.get("in") != "query":
                    continue
                name = param.get("name")
                schema = param.get("schema", {})
                if name == "limit":
                    checked_count += 1
                    max_val = _extract_boundary(schema, "maximum", "le")
                    min_val = _extract_boundary(schema, "minimum", "ge")
                    assert max_val is not None, f"Parameter 'limit' in {method.upper()} {path} lacks maximum boundary"
                    assert max_val <= 200, f"Parameter 'limit' maximum ({max_val}) in {method.upper()} {path} exceeds 200"
                    if min_val is not None:
                        assert min_val >= 1, f"Parameter 'limit' minimum ({min_val}) in {method.upper()} {path} < 1"
                elif name == "offset":
                    checked_count += 1
                    min_val = _extract_boundary(schema, "minimum", "ge")
                    assert min_val is not None, f"Parameter 'offset' in {method.upper()} {path} lacks minimum boundary"
                    assert min_val >= 0, f"Parameter 'offset' minimum ({min_val}) in {method.upper()} {path} < 0"

    assert checked_count > 0, "No pagination parameters were found across OpenAPI paths"


def test_api_v1_documented_endpoints_exist_in_frozen_openapi(openapi_schema: dict[str, Any]) -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    doc_path = backend_dir / "API_V1.md"
    assert doc_path.exists(), f"API_V1.md not found at {doc_path}"

    content = doc_path.read_text(encoding="utf-8")
    pattern = re.compile(r"`(GET|POST|PATCH|DELETE)\s+(/[^`\s]+)`")
    matches = pattern.findall(content)
    assert len(matches) > 0, "No documented endpoints found in API_V1.md"

    paths = openapi_schema["paths"]
    for method, path in matches:
        assert path in paths, f"Documented path '{path}' in API_V1.md does not exist in frozen OpenAPI"
        assert method.lower() in paths[path], (
            f"Documented method '{method}' for '{path}' in API_V1.md does not exist in frozen OpenAPI"
        )
