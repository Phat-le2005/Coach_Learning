from __future__ import annotations

import ast
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Automated and student-facing selection paths that must use the shared
# QuestionGroup-child exclusion predicate. Counts make newly removed call sites
# fail loudly while allowing a module to add further protected selectors.
SELECTOR_MODULES = {
    "app/practice/service.py": 2,
    "app/recommendations/question_service.py": 1,
    "app/recommendations/priority_service.py": 2,
    "app/diagnostics/selector.py": 1,
    "app/diagnostics/blueprint.py": 1,
    "app/repair/service.py": 3,
    "app/exams/blueprint_service.py": 2,
    "app/learning/service.py": 4,
    "app/assignments/service.py": 4,
    "app/synthetic_student_service.py": 2,
    "app/questions/service.py": 1,
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _selects_approved_question(node: ast.AST) -> bool:
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Compare) or len(candidate.ops) != 1:
            continue
        left = candidate.left
        right = candidate.comparators[0]
        if (
            isinstance(candidate.ops[0], ast.Eq)
            and isinstance(left, ast.Attribute)
            and isinstance(left.value, ast.Name)
            and left.value.id == "Question"
            and left.attr == "status"
            and isinstance(right, ast.Attribute)
            and isinstance(right.value, ast.Name)
            and right.value.id == "QuestionStatus"
            and right.attr == "APPROVED"
        ):
            return True
    return False


@pytest.mark.parametrize(
    ("relative_path", "expected_calls"), SELECTOR_MODULES.items()
)
def test_automated_selectors_use_shared_group_child_isolation(
    relative_path: str, expected_calls: int
) -> None:
    source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) == "standalone_question_only"
    ]

    assert "from app.questions.eligibility import standalone_question_only" in source
    assert len(calls) >= expected_calls


def test_every_approved_selector_where_clause_uses_shared_predicate() -> None:
    """Audit SQL selectors while exempting staff Question Bank browsing."""

    automated_modules = set(SELECTOR_MODULES) - {"app/questions/service.py"}
    failures: list[str] = []
    for relative_path in sorted(automated_modules):
        source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) != "where":
                continue
            clause = ast.dump(node, include_attributes=False)
            if _selects_approved_question(node) and "standalone_question_only" not in clause:
                failures.append(f"{relative_path}:{getattr(node, 'lineno', '?')}")

    assert failures == []
