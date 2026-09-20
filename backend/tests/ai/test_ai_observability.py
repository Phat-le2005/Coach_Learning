from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session

from app.ai.models import AIRequestLog
from app.ai.pricing import calculate_estimated_cost, get_model_pricing
from app.ai.types import AITaskType
from app.ai.usage_service import AIUsageService
from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.core.config import Settings
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService
from tests.migrations import load_migration

TEST_PASSWORD = "AI-Observability-Secret-2026!"


def create_test_user(db_session: Session, role: Role, email: str) -> User:
    return UserService(db_session).create_user(
        UserCreate(
            email=email,
            password=TEST_PASSWORD,
            full_name=f"{role.value.title()} User",
            role=role,
        )
    )


def get_auth_headers(db_session: Session, settings: Settings, user: User) -> dict[str, str]:
    tokens = AuthService(db_session, settings).login(
        LoginRequest(email=user.email, password=TEST_PASSWORD)
    )
    return {"Authorization": f"Bearer {tokens.access_token}"}


# --------------------------------------------------------------------------
# 1. Migration Tests
# --------------------------------------------------------------------------

def test_ai_request_log_migration_downgrade_and_upgrade(db_engine: Engine) -> None:
    migration = load_migration("0020_ai_request_log")
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {"ai_request_logs"}
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before


# --------------------------------------------------------------------------
# 2. Pricing Configuration and Cost Calculation Tests
# --------------------------------------------------------------------------

def test_pricing_calculation():
    # Gemini 2.5 Flash: input $0.075 / 1M, output $0.30 / 1M
    cost_flash = calculate_estimated_cost(
        model="gemini-2.5-flash",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert cost_flash == 0.375

    # Small token counts
    cost_small = calculate_estimated_cost(
        model="gemini-2.5-flash",
        input_tokens=1000,
        output_tokens=200,
    )
    # (1000 / 1M * 0.075) + (200 / 1M * 0.30) = 0.000075 + 0.000060 = 0.000135
    assert cost_small == 0.000135

    # Unknown or mock models default to 0.0
    assert calculate_estimated_cost(model="mock", input_tokens=500, output_tokens=500) == 0.0
    assert calculate_estimated_cost(model="unknown-provider-model", input_tokens=500, output_tokens=500) == 0.0

    # Handles None or negative tokens safely
    assert calculate_estimated_cost(model="gemini-2.5-flash", input_tokens=None, output_tokens=None) == 0.0


# --------------------------------------------------------------------------
# 3. Privacy-by-Design Verification
# --------------------------------------------------------------------------

def test_data_privacy_no_raw_prompt_stored():
    """Verify that AIRequestLog NEVER stores raw prompt or raw response texts."""
    columns = {c.name for c in AIRequestLog.__table__.columns}
    assert "prompt_text" not in columns
    assert "raw_prompt" not in columns
    assert "prompt_content" not in columns
    assert "raw_response" not in columns
    assert "completion_text" not in columns
    assert "content" not in columns

    # Metadata columns only
    assert "prompt_name" in columns
    assert "prompt_version" in columns


# --------------------------------------------------------------------------
# 4. AIUsageService Logging and Analytics Tests
# --------------------------------------------------------------------------

def test_record_log_and_query_summary(db_session: Session):
    service = AIUsageService(db_session)
    user = create_test_user(db_session, Role.STUDENT, "ai_student@example.com")

    # Record successful requests
    service.record_log(
        user_id=user.id,
        task=AITaskType.HINT,
        provider="gemini",
        model="gemini-2.5-flash",
        latency_ms=120.5,
        prompt_name="math_hint",
        prompt_version="v2",
        input_tokens=500,
        output_tokens=150,
        success=True,
    )

    service.record_log(
        user_id=user.id,
        task=AITaskType.HINT,
        provider="gemini",
        model="gemini-2.5-flash",
        latency_ms=180.0,
        prompt_name="math_hint",
        prompt_version="v2",
        input_tokens=600,
        output_tokens=200,
        success=True,
    )

    # Record failed request
    service.record_log(
        user_id=user.id,
        task=AITaskType.EXAM_ANALYSIS,
        provider="gemini",
        model="gemini-2.5-pro",
        latency_ms=2500.0,
        prompt_name="exam_matrix",
        prompt_version="v1",
        input_tokens=2000,
        output_tokens=0,
        success=False,
        error_type="AI_SERVICE_UNAVAILABLE",
    )

    # 1. Query logs pagination
    paged = service.get_logs(page=1, page_size=2)
    assert paged.total == 3
    assert len(paged.items) == 2
    assert paged.total_pages == 2

    # Query filtered by task
    paged_hint = service.get_logs(task="HINT")
    assert paged_hint.total == 2
    assert all(item.task == "HINT" for item in paged_hint.items)

    # Query filtered by success=False
    paged_failed = service.get_logs(success=False)
    assert paged_failed.total == 1
    assert paged_failed.items[0].error_type == "AI_SERVICE_UNAVAILABLE"

    # 2. Query usage summary
    summary = service.get_usage_summary()
    assert summary.total_requests == 3
    assert summary.successful_requests == 2
    assert summary.failed_requests == 1
    assert summary.failure_rate == round(1 / 3, 4)
    # Average latency: (120.5 + 180.0 + 2500.0) / 3 = 2800.5 / 3 = 933.5
    assert summary.average_latency_ms == pytest.approx(933.5, rel=1e-2)
    assert summary.total_input_tokens == 3100
    assert summary.total_output_tokens == 350
    assert summary.total_tokens == 3450
    assert summary.total_estimated_cost > 0.0

    # Task metrics breakdown
    task_map = {t.task: t for t in summary.requests_per_task}
    assert "HINT" in task_map
    assert task_map["HINT"].requests == 2
    assert task_map["HINT"].failure_rate == 0.0
    assert "EXAM_ANALYSIS" in task_map
    assert task_map["EXAM_ANALYSIS"].requests == 1
    assert task_map["EXAM_ANALYSIS"].failure_rate == 1.0

    # Daily metrics breakdown
    assert len(summary.requests_per_day) >= 1
    assert summary.requests_per_day[0].requests == 3


# --------------------------------------------------------------------------
# 5. Admin API RBAC and Endpoint Tests
# --------------------------------------------------------------------------

def test_admin_api_unauthorized_access(db_client: TestClient):
    # No auth header
    res1 = db_client.get("/admin/ai/usage")
    assert res1.status_code == 401

    res2 = db_client.get("/admin/ai/usage/summary")
    assert res2.status_code == 401


def test_admin_api_non_admin_forbidden(
    db_client: TestClient,
    db_session: Session,
    settings: Settings,
):
    student = create_test_user(db_session, Role.STUDENT, "stud1@example.com")
    student_headers = get_auth_headers(db_session, settings, student)

    res = db_client.get("/admin/ai/usage", headers=student_headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"

    res_sum = db_client.get("/admin/ai/usage/summary", headers=student_headers)
    assert res_sum.status_code == 403


def test_admin_api_authorized_access(
    db_client: TestClient,
    db_session: Session,
    settings: Settings,
):
    admin = create_test_user(db_session, Role.ADMIN, "admin_user@example.com")
    admin_headers = get_auth_headers(db_session, settings, admin)

    # Insert test log
    service = AIUsageService(db_session)
    service.record_log(
        user_id=admin.id,
        task=AITaskType.TEACHER_COPILOT,
        provider="mock",
        model="gemini-2.5-standard",
        latency_ms=95.0,
        prompt_name="lesson_plan",
        prompt_version="v1",
        input_tokens=100,
        output_tokens=50,
        success=True,
    )
    db_session.commit()

    # Test GET /admin/ai/usage
    res_usage = db_client.get("/admin/ai/usage?page=1&page_size=10", headers=admin_headers)
    assert res_usage.status_code == 200
    assert res_usage.headers.get("Cache-Control") == "no-store"
    data_usage = res_usage.json()
    assert "items" in data_usage
    assert data_usage["total"] >= 1
    assert data_usage["items"][0]["task"] == "TEACHER_COPILOT"

    # Test GET /admin/ai/usage/summary
    res_summary = db_client.get("/admin/ai/usage/summary", headers=admin_headers)
    assert res_summary.status_code == 200
    assert res_summary.headers.get("Cache-Control") == "no-store"
    data_summary = res_summary.json()
    assert data_summary["total_requests"] >= 1
    assert "requests_per_day" in data_summary
    assert "requests_per_task" in data_summary
    assert "tokens_per_task" in data_summary
