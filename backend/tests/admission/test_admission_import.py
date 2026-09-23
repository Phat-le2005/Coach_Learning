from collections.abc import Callable
from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admission.adapters import MockMoetAdmissionPortalAdapter, OfficialAdmissionSourceAdapter
from app.admission.import_schemas import AdmissionImportAction, AdmissionRuleImportRecord
from app.admission.import_service import AdmissionImportService
from app.admission.models import (
    AdmissionDataSource,
    AdmissionImportFormat,
    AdmissionImportHistory,
    AdmissionImportStatus,
    AdmissionMethod,
    AdmissionRule,
    Major,
    University,
)
from app.users.models import Role, User


SAMPLE_CSV_CONTENT = """university_code,major_code,method_code,year,subject_combination,requirements,quota,historical_score,source_reference,verified_at,data_source_name
BKHN,IT1,THPT,2026,A00,"{""floor_score"": 25.0}",160,29.42,Đề án tuyển sinh BKHN 2026 Mục 1.1,2026-03-15T08:00:00Z,Đề án ĐHBKHN 2026
BKHN,IT1,THPT,2026,A01,"{""floor_score"": 24.5}",80,,Đề án tuyển sinh BKHN 2026 Mục 1.2,2026-03-15T08:00:00Z,Đề án ĐHBKHN 2026
FTU,NTH01,THPT,2026,D01,"{""english_min"": 8.0}",120,28.5,Đề án FTU 2026 Mục 2.1,2026-03-15T08:00:00Z,Đề án FTU 2026
"""

SAMPLE_INVALID_CSV = """university_code,major_code,method_code,year,subject_combination,requirements,quota,historical_score,source_reference,verified_at,data_source_name
BKHN,IT1,THPT,1995,A00,{},100,28.0,Nguồn cũ,2026-01-01T00:00:00Z,Đề án cũ
FTU,NTH01,THPT,2026,D01,{},-10,28.0,Nguồn FTU,2026-01-01T00:00:00Z,Đề án FTU
HCMUT,CS1,THPT,2026,A00,{},100,28.0,,2026-01-01T00:00:00Z,Đề án HCMUT
HCMUT,CS1,THPT,2026,A00,{},100,28.0,Nguồn HCMUT,,Đề án HCMUT
HCMUT,CS1,THPT,2026,A00,{},100,28.0,Nguồn HCMUT,2026-01-01T00:00:00Z,
"""


# --------------------------------------------------------------------------
# 1. CSV Parse, Validate & Preview Stage Tests
# --------------------------------------------------------------------------

def test_csv_parse_and_preview_pipeline(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    admin_user = admission_user_factory(Role.ADMIN, "admin_import_csv@example.com")
    headers = admission_bearer(admin_user)

    # Call preview with valid CSV content
    files = {"file": ("admission_2026.csv", SAMPLE_CSV_CONTENT.encode("utf-8"), "text/csv")}
    res = db_client.post("/admission/import/preview", headers=headers, files=files)
    assert res.status_code == 201, res.text

    data = res.json()
    assert data["status"] == "PREVIEWED"
    assert data["file_format"] == "CSV"
    assert data["total_rows"] == 3
    assert data["valid_rows"] == 3
    assert data["error_rows"] == 0
    assert data["insert_count"] == 3
    assert data["target_years"] == [2026]
    assert len(data["rows"]) == 3

    row1 = data["rows"][0]
    assert row1["university_code"] == "BKHN"
    assert row1["major_code"] == "IT1"
    assert row1["subject_combination"] == "A00"
    assert row1["action"] == "INSERT"
    assert "Đề án ĐHBKHN 2026" in row1["data_source_name"]


# --------------------------------------------------------------------------
# 2. JSON Parse & Preview (Envelope & Array formats)
# --------------------------------------------------------------------------

def test_json_parse_and_preview_envelope_format(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    admin_user = admission_user_factory(Role.ADMIN, "admin_import_json@example.com")
    headers = admission_bearer(admin_user)

    envelope_payload = {
        "year": 2026,
        "data_source_name": "Cổng tuyển sinh Đại học Bách Khoa 2026",
        "data_source_url": "https://ts.hust.edu.vn",
        "source_reference": "Thông báo tuyển sinh số 102/TB-ĐHBKHN",
        "verified_at": "2026-03-20T10:00:00Z",
        "rules": [
            {
                "university_code": "bkhn",  # test auto uppercase
                "major_code": "it1",
                "method_code": "thpt",
                "subject_combination": "a00",
                "quota": 170,
                "requirements": {"math_weight": 2.0},
            },
            {
                "university_code": "BKHN",
                "major_code": "EE1",
                "method_code": "THPT",
                "subject_combination": "A00",
                "quota": 100,
            },
        ],
    }

    res = db_client.post(
        "/admission/import/preview-payload",
        headers=headers,
        json=envelope_payload,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["total_rows"] == 2
    assert data["valid_rows"] == 2
    assert data["error_rows"] == 0
    assert data["target_years"] == [2026]

    # Verify uppercase normalization
    codes = {r["major_code"] for r in data["rows"]}
    assert codes == {"IT1", "EE1"}
    # Verify inherited envelope metadata
    for r in data["rows"]:
        assert r["source_reference"] == "Thông báo tuyển sinh số 102/TB-ĐHBKHN"
        assert r["data_source_name"] == "Cổng tuyển sinh Đại học Bách Khoa 2026"


# --------------------------------------------------------------------------
# 3. Strict Source Verification Fields Enforcement Tests
# --------------------------------------------------------------------------

def test_source_verification_fields_enforcement(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    admin_user = admission_user_factory(Role.ADMIN, "admin_import_verify@example.com")
    headers = admission_bearer(admin_user)

    files = {"file": ("invalid_sources.csv", SAMPLE_INVALID_CSV.encode("utf-8"), "text/csv")}
    res = db_client.post("/admission/import/preview", headers=headers, files=files)
    assert res.status_code == 201, res.text

    data = res.json()
    assert data["total_rows"] == 5
    assert data["valid_rows"] == 0
    assert data["error_rows"] == 5

    # Check errors recorded per row
    error_rows = {err["row_number"]: err["message"] for err in data["errors"]}
    assert 1 in error_rows  # year < 2000
    assert 2 in error_rows  # quota < 0
    assert 3 in error_rows  # missing source_reference
    assert 4 in error_rows  # missing verified_at
    assert 5 in error_rows  # missing data_source


# --------------------------------------------------------------------------
# 4. Idempotent Import & Full Provenance Audit Tests
# --------------------------------------------------------------------------

def test_idempotent_import_and_provenance(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    admin_user = admission_user_factory(Role.ADMIN, "admin_idempotent@example.com")
    headers = admission_bearer(admin_user)

    files = {"file": ("batch_2026.csv", SAMPLE_CSV_CONTENT.encode("utf-8"), "text/csv")}
    res_preview = db_client.post("/admission/import/preview", headers=headers, files=files)
    assert res_preview.status_code == 201
    batch_id = res_preview.json()["batch_id"]

    # 1. First execution: Inserts 3 new rules
    res_exec1 = db_client.post(
        "/admission/import/execute",
        headers=headers,
        json={"batch_id": batch_id, "auto_create_entities": True},
    )
    assert res_exec1.status_code == 200, res_exec1.text
    exec1_data = res_exec1.json()
    assert exec1_data["status"] == "COMPLETED"
    assert exec1_data["imported_rows"] == 3
    assert exec1_data["updated_rows"] == 0

    # Verify rules in database have import_history_id attached
    rules_in_db = db_session.scalars(
        select(AdmissionRule).where(AdmissionRule.year == 2026)
    ).all()
    assert len(rules_in_db) == 3
    for r in rules_in_db:
        assert str(r.import_history_id) == batch_id
        assert r.verified_at is not None
        assert r.source_reference is not None
        assert r.verified_by == admin_user.id

    # 2. Re-executing the same batch (idempotence): returns identical results without error
    res_exec_re = db_client.post(
        "/admission/import/execute",
        headers=headers,
        json={"batch_id": batch_id, "auto_create_entities": True},
    )
    assert res_exec_re.status_code == 200
    assert res_exec_re.json()["status"] == "COMPLETED"
    assert res_exec_re.json()["imported_rows"] == 3

    # Total rules in database must still be exactly 3
    rules_count = len(
        db_session.scalars(select(AdmissionRule).where(AdmissionRule.year == 2026)).all()
    )
    assert rules_count == 3

    # 3. Import same payload in a NEW batch (diff check -> UPDATE/NO_CHANGE, 0 duplicate rules)
    files2 = {"file": ("batch_2026_repeat.csv", SAMPLE_CSV_CONTENT.encode("utf-8"), "text/csv")}
    res_preview2 = db_client.post("/admission/import/preview", headers=headers, files=files2)
    assert res_preview2.status_code == 201
    batch2_id = res_preview2.json()["batch_id"]
    assert res_preview2.json()["no_change_count"] == 3  # All 3 detected as NO_CHANGE

    res_exec2 = db_client.post(
        "/admission/import/execute",
        headers=headers,
        json={"batch_id": batch2_id, "auto_create_entities": True},
    )
    assert res_exec2.status_code == 200
    # Updated rules in-place, 0 new rows created
    assert res_exec2.json()["imported_rows"] == 0
    assert res_exec2.json()["updated_rows"] == 3

    rules_count_final = len(
        db_session.scalars(select(AdmissionRule).where(AdmissionRule.year == 2026)).all()
    )
    assert rules_count_final == 3  # Still strictly 3 rules!


# --------------------------------------------------------------------------
# 5. Year Isolation Guarantee: Do NOT Overwrite Other Years
# --------------------------------------------------------------------------

def test_year_isolation_guarantee(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    admin_user = admission_user_factory(Role.ADMIN, "admin_year_iso@example.com")
    headers = admission_bearer(admin_user)

    # 1. Pre-seed year 2025 rule for BKHN - IT1 - A00
    service = AdmissionImportService(db_session)
    u = University(code="BKHN", name="Đại học Bách Khoa Hà Nội")
    m = Major(university=u, code="IT1", name="Khoa học Máy tính")
    pt = AdmissionMethod(code="THPT", name="Thi tốt nghiệp THPT")
    ds = AdmissionDataSource(name="Đề án 2025", published_year=2025)
    db_session.add_all([u, m, pt, ds])
    db_session.flush()

    rule_2025 = AdmissionRule(
        university=u,
        major=m,
        year=2025,
        method=pt,
        subject_combination="A00",
        quota=150,
        historical_score=29.42,
        requirements={"floor_score": 24.0},
        source_reference="Đề án 2025 BKHN",
        data_source=ds,
        verified_at=datetime.now(timezone.utc),
    )
    db_session.add(rule_2025)
    db_session.commit()
    rule_2025_id = rule_2025.id

    # 2. Import year 2026 rule for the SAME university, major, and combination
    payload_2026 = {
        "year": 2026,
        "data_source_name": "Đề án 2026 BKHN",
        "source_reference": "Đề án 2026 BKHN Mục 1.1",
        "verified_at": "2026-03-01T00:00:00Z",
        "rules": [
            {
                "university_code": "BKHN",
                "major_code": "IT1",
                "method_code": "THPT",
                "subject_combination": "A00",
                "quota": 190,  # different quota
                "requirements": {"floor_score": 26.0},  # different floor
            }
        ],
    }

    res_prev = db_client.post(
        "/admission/import/preview-payload",
        headers=headers,
        json=payload_2026,
    )
    assert res_prev.status_code == 201
    batch_id = res_prev.json()["batch_id"]

    res_exec = db_client.post(
        "/admission/import/execute",
        headers=headers,
        json={"batch_id": batch_id, "auto_create_entities": True},
    )
    assert res_exec.status_code == 200

    # 3. VERIFY YEAR ISOLATION GUARANTEE:
    # 2025 rule must be completely UNTOUCHED!
    db_session.expire_all()
    rule_2025_check = db_session.get(AdmissionRule, rule_2025_id)
    assert rule_2025_check is not None
    assert rule_2025_check.year == 2025
    assert rule_2025_check.quota == 150  # Must NOT be overwritten to 190
    assert rule_2025_check.historical_score == 29.42
    assert rule_2025_check.requirements == {"floor_score": 24.0}

    # 2026 rule must be present with new values
    rule_2026_check = db_session.scalar(
        select(AdmissionRule).where(
            AdmissionRule.major_id == m.id,
            AdmissionRule.year == 2026,
            AdmissionRule.subject_combination == "A00",
        )
    )
    assert rule_2026_check is not None
    assert rule_2026_check.quota == 190
    assert rule_2026_check.requirements == {"floor_score": 26.0}


# --------------------------------------------------------------------------
# 6. Official Admission Source Adapter Interface Tests
# --------------------------------------------------------------------------

def test_official_source_adapter_integration(
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
) -> None:
    admin_user = admission_user_factory(Role.ADMIN, "admin_adapter@example.com")
    adapter = MockMoetAdmissionPortalAdapter()

    assert adapter.source_identifier == "MOET_OFFICIAL_PORTAL"
    assert adapter.verify_source_authenticity("Đề án tuyển sinh Bộ GD&ĐT 2026") is True
    assert adapter.verify_source_authenticity("short") is False

    # Fetch records via adapter
    records = adapter.fetch_admission_rules(year=2026)
    assert len(records) == 1
    rec = records[0]
    assert rec.university_code == "BKHN"
    assert rec.year == 2026

    # Feed into import service directly
    service = AdmissionImportService(db_session)
    payload_bytes = json.dumps([rec.model_dump(mode="json")]).encode("utf-8")
    preview = service.preview(
        actor_id=admin_user.id,
        file_name="moet_feed_2026.json",
        file_format=AdmissionImportFormat.DIRECT_FEED,
        content=payload_bytes,
    )
    assert preview.total_rows == 1
    assert preview.valid_rows == 1

    exec_result = service.execute_import(
        batch_id=preview.batch_id,
        actor_id=admin_user.id,
        auto_create_entities=True,
    )
    assert exec_result.imported_rows == 1
    assert exec_result.status == AdmissionImportStatus.COMPLETED


# --------------------------------------------------------------------------
# 7. Authorization and History Endpoints Tests
# --------------------------------------------------------------------------

def test_import_authorization_and_history_apis(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "student_import@example.com")
    admin_user = admission_user_factory(Role.ADMIN, "admin_history@example.com")

    student_headers = admission_bearer(student_user)
    admin_headers = admission_bearer(admin_user)

    # 1. Unauthenticated requests return 401
    assert db_client.post("/admission/import/preview-payload", json={}).status_code == 401
    assert db_client.post("/admission/import/execute", json={"batch_id": str(uuid4())}).status_code == 401
    assert db_client.get("/admission/import/history").status_code == 401

    # 2. Student requests return 403 Forbidden
    assert db_client.post("/admission/import/preview-payload", headers=student_headers, json={}).status_code == 403
    assert db_client.post("/admission/import/execute", headers=student_headers, json={"batch_id": str(uuid4())}).status_code == 403
    assert db_client.get("/admission/import/history", headers=student_headers).status_code == 403

    # 3. Admin successfully previews and executes
    payload = {
        "year": 2026,
        "data_source_name": "Đề án Kiểm thử Lịch sử",
        "source_reference": "Văn bản mẫu",
        "verified_at": "2026-03-01T00:00:00Z",
        "rules": [
            {
                "university_code": "UEH",
                "major_code": "FIN1",
                "method_code": "THPT",
                "subject_combination": "A01",
                "quota": 100,
            }
        ],
    }
    res_p = db_client.post("/admission/import/preview-payload", headers=admin_headers, json=payload)
    assert res_p.status_code == 201
    batch_id = res_p.json()["batch_id"]

    # 4. GET /admission/import/history
    res_hist = db_client.get("/admission/import/history", headers=admin_headers)
    assert res_hist.status_code == 200
    histories = res_hist.json()
    assert len(histories) >= 1
    assert any(h["id"] == batch_id for h in histories)

    # 5. GET /admission/import/history/{id}
    res_detail = db_client.get(f"/admission/import/history/{batch_id}", headers=admin_headers)
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["id"] == batch_id
    assert detail["status"] == "PREVIEWED"
    assert detail["total_rows"] == 1
