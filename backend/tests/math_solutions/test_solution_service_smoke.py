"""STEP-CORE-01 focused service tests.

These cover rejection and ownership without mutating a running database.
Full lifecycle tests require disposable PostgreSQL and remain a release gate.
"""
from uuid import uuid4

import pytest
from unittest.mock import MagicMock

from app.core.exceptions import ApplicationError
from app.math_solutions.service import MathSolutionService, _digest
from app.math_solutions.schemas import SolutionStepDraft


def test_request_digest_is_order_independent():
    assert _digest({"operation": "ADD_STEP", "payload": {"a": 1, "b": 2}}) == _digest(
        {"payload": {"b": 2, "a": 1}, "operation": "ADD_STEP"}
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"step_type": "CUSTOM", "content_latex": " ", "explanation_text": ""},
        {"step_type": "SIGN_TABLE", "content_latex": None, "explanation_text": None},
    ],
)
def test_empty_step_is_rejected(payload):
    with pytest.raises(ValueError):
        SolutionStepDraft.model_validate(payload)


def test_unowned_attempt_cannot_be_read():
    session = MagicMock()
    session.scalar.return_value = None
    with pytest.raises(ApplicationError) as raised:
        MathSolutionService(session).get(uuid4(), uuid4())
    assert raised.value.status_code == 403


def test_teacher_or_unknown_user_cannot_create_solution():
    session = MagicMock()
    session.scalar.return_value = None
    with pytest.raises(ApplicationError) as raised:
        MathSolutionService(session).create(
            uuid4(), source_kind="CANONICAL", context_type="SELF_PRACTICE",
            mode="GUIDED_LEARNING", create_idempotency_key="a1",
            question_id=uuid4(), practice_session_id=uuid4(),
        )
    assert raised.value.status_code == 403
