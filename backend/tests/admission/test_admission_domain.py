from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admission.models import (
    AdmissionDataSource,
    AdmissionMethod,
    AdmissionRule,
    AdmissionTarget,
    AdmissionTargetType,
    Major,
    University,
)
from app.admission.schemas import (
    AdmissionDataSourceCreate,
    AdmissionMethodCreate,
    AdmissionRuleCreate,
    AdmissionTargetCreate,
    AdmissionTargetUpdate,
    MajorCreate,
    UniversityCreate,
)
from app.admission.service import AdmissionService
from app.students.models import StudentProfile
from app.users.models import Role, User


def _seed_admission_catalog(
    session: Session, admin_id: UUID | None = None
) -> tuple[University, University, Major, Major, Major, AdmissionMethod, AdmissionMethod]:
    service = AdmissionService(session)

    u1 = service.create_university(
        UniversityCreate(
            code="BKHN",
            name="Đại học Bách Khoa Hà Nội",
            short_name="HUST",
            description="Đại học kỹ thuật hàng đầu Việt Nam",
            website="https://hust.edu.vn",
            region="MIEN_BAC",
        )
    )
    u2 = service.create_university(
        UniversityCreate(
            code="FTU",
            name="Trường Đại học Ngoại Thương",
            short_name="FTU",
            description="Trường đại học chuyên ngành kinh tế, thương mại",
            website="https://ftu.edu.vn",
            region="MIEN_BAC",
        )
    )
    u3 = service.create_university(
        UniversityCreate(
            code="HCMUT",
            name="Trường Đại học Bách Khoa - ĐHQG TP.HCM",
            short_name="HCMUT",
            description="Đại học kỹ thuật phía Nam",
            website="https://hcmut.edu.vn",
            region="MIEN_NAM",
        )
    )

    m1 = service.create_major(
        MajorCreate(
            university_id=u1.id,
            code="IT1",
            name="Khoa học Máy tính",
            description="Chương trình chuẩn Khoa học máy tính",
        )
    )
    m2 = service.create_major(
        MajorCreate(
            university_id=u1.id,
            code="EE1",
            name="Kỹ thuật Điều khiển và Tự động hóa",
            description="Chương trình chuẩn Tự động hóa",
        )
    )
    m3 = service.create_major(
        MajorCreate(
            university_id=u2.id,
            code="NTH01",
            name="Kinh tế đối ngoại",
            description="Chuyên ngành Kinh tế đối ngoại",
        )
    )

    method_thpt = service.create_method(
        AdmissionMethodCreate(
            code="THPT",
            name="Xét tuyển theo kết quả thi tốt nghiệp THPT",
            description="Điểm thi tốt nghiệp THPT quốc gia theo các tổ hợp",
        )
    )
    method_hsa = service.create_method(
        AdmissionMethodCreate(
            code="DGNL_HSA",
            name="Xét tuyển theo kỳ thi ĐGNL ĐHQGHN (HSA)",
            description="Kỳ thi đánh giá năng lực của Đại học Quốc gia Hà Nội",
        )
    )

    ds_2025 = service.create_data_source(
        AdmissionDataSourceCreate(
            name="Đề án Tuyển sinh Đại học Bách Khoa Hà Nội năm 2025",
            source_type="OFFICIAL_PROSPECTUS",
            source_url="https://ts.hust.edu.vn/de-an-2025.pdf",
            publisher="Đại học Bách Khoa Hà Nội",
            published_year=2025,
            verified_at=datetime.now(timezone.utc),
            verified_by=admin_id,
        )
    )
    ds_2026 = service.create_data_source(
        AdmissionDataSourceCreate(
            name="Thông báo tuyển sinh Đại học Bách Khoa Hà Nội năm 2026",
            source_type="OFFICIAL_PROSPECTUS",
            source_url="https://ts.hust.edu.vn/de-an-2026.pdf",
            publisher="Đại học Bách Khoa Hà Nội",
            published_year=2026,
            verified_at=datetime.now(timezone.utc),
            verified_by=admin_id,
        )
    )

    # 2025 Rules for IT1
    service.create_rule(
        AdmissionRuleCreate(
            university_id=u1.id,
            major_id=m1.id,
            year=2025,
            method_id=method_thpt.id,
            subject_combination="A00",
            requirements={"math_minimum": 8.0, "floor_score": 24.0},
            quota=150,
            historical_score=29.42,
            source_reference="Quy chế 2025 BKHN, Mục 3.1",
            data_source_id=ds_2025.id,
            verified_at=datetime.now(timezone.utc),
        )
    )
    service.create_rule(
        AdmissionRuleCreate(
            university_id=u1.id,
            major_id=m1.id,
            year=2025,
            method_id=method_hsa.id,
            subject_combination="HSA",
            requirements={"hsa_minimum": 90.0},
            quota=100,
            historical_score=98.5,
            source_reference="Quy chế 2025 BKHN, Mục 3.2",
            data_source_id=ds_2025.id,
            verified_at=datetime.now(timezone.utc),
        )
    )

    # 2026 Rules for IT1
    service.create_rule(
        AdmissionRuleCreate(
            university_id=u1.id,
            major_id=m1.id,
            year=2026,
            method_id=method_thpt.id,
            subject_combination="A00",
            requirements={"math_minimum": 8.5, "floor_score": 25.0},
            quota=160,
            historical_score=None,
            source_reference="Đề án tuyển sinh 2026 BKHN",
            data_source_id=ds_2026.id,
            verified_at=datetime.now(timezone.utc),
        )
    )
    service.create_rule(
        AdmissionRuleCreate(
            university_id=u1.id,
            major_id=m1.id,
            year=2026,
            method_id=method_thpt.id,
            subject_combination="A01",
            requirements={"floor_score": 24.5},
            quota=80,
            historical_score=None,
            source_reference="Đề án tuyển sinh 2026 BKHN",
            data_source_id=ds_2026.id,
            verified_at=datetime.now(timezone.utc),
        )
    )

    return u1, u2, m1, m2, m3, method_thpt, method_hsa


# --------------------------------------------------------------------------
# 1. Catalog Tests (Universities & Majors)
# --------------------------------------------------------------------------

def test_universities_and_majors_catalog_apis(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "student_catalog@example.com")
    headers = admission_bearer(student_user)

    u1, u2, m1, m2, m3, _, _ = _seed_admission_catalog(db_session, student_user.id)

    # GET /admission/universities
    res = db_client.get("/admission/universities", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert len(data) == 3
    bkhn = next(u for u in data if u["code"] == "BKHN")
    assert bkhn["name"] == "Đại học Bách Khoa Hà Nội"
    assert bkhn["majors_count"] == 2

    # Test search by name/short_name
    res_search = db_client.get("/admission/universities?search=Bách Khoa", headers=headers)
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert len(search_data) == 2
    codes = {u["code"] for u in search_data}
    assert codes == {"BKHN", "HCMUT"}

    # Test region filter
    res_region = db_client.get("/admission/universities?region=MIEN_NAM", headers=headers)
    assert res_region.status_code == 200
    region_data = res_region.json()
    assert len(region_data) == 1
    assert region_data[0]["code"] == "HCMUT"

    # GET /admission/universities/{id}/majors
    res_majors = db_client.get(f"/admission/universities/{u1.id}/majors", headers=headers)
    assert res_majors.status_code == 200
    majors_data = res_majors.json()
    assert len(majors_data) == 2
    major_codes = [m["code"] for m in majors_data]
    assert "EE1" in major_codes
    assert "IT1" in major_codes

    # Search inside majors
    res_major_search = db_client.get(
        f"/admission/universities/{u1.id}/majors?search=Máy tính", headers=headers
    )
    assert res_major_search.status_code == 200
    assert len(res_major_search.json()) == 1
    assert res_major_search.json()[0]["code"] == "IT1"

    # 404 for non-existent university
    res_404 = db_client.get(f"/admission/universities/{uuid4()}/majors", headers=headers)
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "UNIVERSITY_NOT_FOUND"


# --------------------------------------------------------------------------
# 2. Admission Rules Versioned by Year Tests
# --------------------------------------------------------------------------

def test_admission_rules_versioned_by_year_apis(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "student_rules@example.com")
    headers = admission_bearer(student_user)

    u1, _, m1, _, _, _, _ = _seed_admission_catalog(db_session, student_user.id)

    # GET all rules for IT1 without year filter
    res = db_client.get(f"/admission/majors/{m1.id}/rules", headers=headers)
    assert res.status_code == 200, res.text
    rules = res.json()
    assert len(rules) == 4
    years = [r["year"] for r in rules]
    assert 2026 in years
    assert 2025 in years

    # GET rules versioned for year 2025
    res_2025 = db_client.get(f"/admission/majors/{m1.id}/rules?year=2025", headers=headers)
    assert res_2025.status_code == 200
    rules_2025 = res_2025.json()
    assert len(rules_2025) == 2
    for r in rules_2025:
        assert r["year"] == 2025
        assert r["major_name"] == "Khoa học Máy tính"
        assert r["university_name"] == "Đại học Bách Khoa Hà Nội"
    combos_2025 = {r["subject_combination"] for r in rules_2025}
    assert combos_2025 == {"A00", "HSA"}

    rule_a00_2025 = next(r for r in rules_2025 if r["subject_combination"] == "A00")
    assert rule_a00_2025["historical_score"] == 29.42
    assert rule_a00_2025["quota"] == 150
    assert rule_a00_2025["requirements"]["math_minimum"] == 8.0
    assert rule_a00_2025["source_reference"] == "Quy chế 2025 BKHN, Mục 3.1"
    assert rule_a00_2025["verified_at"] is not None

    # GET rules versioned for year 2026
    res_2026 = db_client.get(f"/admission/majors/{m1.id}/rules?year=2026", headers=headers)
    assert res_2026.status_code == 200
    rules_2026 = res_2026.json()
    assert len(rules_2026) == 2
    for r in rules_2026:
        assert r["year"] == 2026
    combos_2026 = {r["subject_combination"] for r in rules_2026}
    assert combos_2026 == {"A00", "A01"}

    # Non-existent major rules returns 404
    res_404 = db_client.get(f"/admission/majors/{uuid4()}/rules", headers=headers)
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "MAJOR_NOT_FOUND"


# --------------------------------------------------------------------------
# 3. Student Admission Targets Lifecycle & Pedagogical Invariance
# --------------------------------------------------------------------------

def test_student_admission_targets_lifecycle(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "student_targets@example.com")
    headers = admission_bearer(student_user)

    u1, u2, m1, m2, m3, _, _ = _seed_admission_catalog(db_session, student_user.id)

    # 1. Initial targets list is empty
    res_empty = db_client.get("/students/me/admission-targets", headers=headers)
    assert res_empty.status_code == 200
    assert res_empty.json() == []

    # 2. Add target 1 (DREAM)
    res_t1 = db_client.post(
        "/students/me/admission-targets",
        headers=headers,
        json={
            "university_id": str(u1.id),
            "major_id": str(m1.id),
            "target_type": "DREAM",
            "target_year": 2026,
            "priority_order": 1,
            "notes": "Nguyện vọng 1 mơ ước ngành Khoa học Máy tính",
        },
    )
    assert res_t1.status_code == 201, res_t1.text
    t1_data = res_t1.json()
    assert t1_data["target_type"] == "DREAM"
    assert t1_data["university_code"] == "BKHN"
    assert t1_data["major_code"] == "IT1"
    assert t1_data["priority_order"] == 1
    t1_id = t1_data["id"]

    # 3. Add target 2 (TARGET)
    res_t2 = db_client.post(
        "/students/me/admission-targets",
        headers=headers,
        json={
            "university_id": str(u1.id),
            "major_id": str(m2.id),
            "target_type": "TARGET",
            "target_year": 2026,
            "priority_order": 2,
            "notes": "Nguyện vọng 2 mục tiêu vừa sức",
        },
    )
    assert res_t2.status_code == 201
    assert res_t2.json()["target_type"] == "TARGET"

    # 4. Add target 3 (SAFE)
    res_t3 = db_client.post(
        "/students/me/admission-targets",
        headers=headers,
        json={
            "university_id": str(u2.id),
            "major_id": str(m3.id),
            "target_type": "SAFE",
            "target_year": 2026,
            "priority_order": 3,
            "notes": "Nguyện vọng 3 an toàn dự phòng",
        },
    )
    assert res_t3.status_code == 201
    assert res_t3.json()["target_type"] == "SAFE"

    # 5. List targets: verify order and invariant category preservation
    res_list = db_client.get("/students/me/admission-targets", headers=headers)
    assert res_list.status_code == 200
    targets = res_list.json()
    assert len(targets) == 3
    # Check priority sorting
    assert [t["priority_order"] for t in targets] == [1, 2, 3]
    # Check strict category invariance: system does not overwrite student-selected category
    assert [t["target_type"] for t in targets] == ["DREAM", "TARGET", "SAFE"]

    # 6. Duplicate target rejection (same student, university, major, year)
    res_dup = db_client.post(
        "/students/me/admission-targets",
        headers=headers,
        json={
            "university_id": str(u1.id),
            "major_id": str(m1.id),
            "target_type": "TARGET",
            "target_year": 2026,
            "priority_order": 4,
        },
    )
    assert res_dup.status_code == 409
    assert res_dup.json()["error"]["code"] == "TARGET_ALREADY_EXISTS"

    # 7. Major university mismatch rejection
    res_mismatch = db_client.post(
        "/students/me/admission-targets",
        headers=headers,
        json={
            "university_id": str(u1.id),  # BKHN
            "major_id": str(m3.id),        # FTU's major
            "target_type": "DREAM",
            "target_year": 2026,
            "priority_order": 5,
        },
    )
    assert res_mismatch.status_code == 400
    assert res_mismatch.json()["error"]["code"] == "MAJOR_UNIVERSITY_MISMATCH"

    # 8. Update target (PATCH)
    res_patch = db_client.patch(
        f"/students/me/admission-targets/{t1_id}",
        headers=headers,
        json={"priority_order": 1, "notes": "Cập nhật ghi chú ôn thi toán điểm cao"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["notes"] == "Cập nhật ghi chú ôn thi toán điểm cao"

    # 9. Delete target (DELETE)
    res_del = db_client.delete(f"/students/me/admission-targets/{t1_id}", headers=headers)
    assert res_del.status_code == 204

    # Verify target was deleted
    res_list_after = db_client.get("/students/me/admission-targets", headers=headers)
    assert res_list_after.status_code == 200
    assert len(res_list_after.json()) == 2
    remaining_ids = {t["id"] for t in res_list_after.json()}
    assert t1_id not in remaining_ids


# --------------------------------------------------------------------------
# 4. Security & Multi-tenant Isolation Tests
# --------------------------------------------------------------------------

def test_admission_security_and_student_isolation(
    db_client: TestClient,
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    admission_bearer: Callable[[User], dict[str, str]],
) -> None:
    s1_user = admission_user_factory(Role.STUDENT, "s1_iso@example.com")
    s2_user = admission_user_factory(Role.STUDENT, "s2_iso@example.com")
    t_user = admission_user_factory(Role.TEACHER, "teacher_iso@example.com")

    s1_headers = admission_bearer(s1_user)
    s2_headers = admission_bearer(s2_user)
    t_headers = admission_bearer(t_user)

    u1, _, m1, _, _, _, _ = _seed_admission_catalog(db_session, s1_user.id)

    # 1. Unauthenticated requests fail with 401
    assert db_client.get("/admission/universities").status_code == 401
    assert db_client.get(f"/admission/universities/{u1.id}/majors").status_code == 401
    assert db_client.get(f"/admission/majors/{m1.id}/rules").status_code == 401
    assert db_client.get("/students/me/admission-targets").status_code == 401
    assert db_client.post("/students/me/admission-targets", json={}).status_code == 401

    # 2. Teacher cannot manage /students/me/admission-targets (403 Forbidden)
    res_t = db_client.get("/students/me/admission-targets", headers=t_headers)
    assert res_t.status_code == 403

    res_t_post = db_client.post(
        "/students/me/admission-targets",
        headers=t_headers,
        json={
            "university_id": str(u1.id),
            "major_id": str(m1.id),
            "target_type": "DREAM",
            "target_year": 2026,
            "priority_order": 1,
        },
    )
    assert res_t_post.status_code == 403

    # 3. Student 1 creates target
    res_s1 = db_client.post(
        "/students/me/admission-targets",
        headers=s1_headers,
        json={
            "university_id": str(u1.id),
            "major_id": str(m1.id),
            "target_type": "DREAM",
            "target_year": 2026,
            "priority_order": 1,
        },
    )
    assert res_s1.status_code == 201
    s1_target_id = res_s1.json()["id"]

    # 4. Student 2 cannot see Student 1's target
    res_s2_list = db_client.get("/students/me/admission-targets", headers=s2_headers)
    assert res_s2_list.status_code == 200
    assert res_s2_list.json() == []

    # 5. Student 2 cannot delete Student 1's target (403)
    res_s2_del = db_client.delete(
        f"/students/me/admission-targets/{s1_target_id}", headers=s2_headers
    )
    assert res_s2_del.status_code == 403

    # 6. Student 2 cannot update Student 1's target (403)
    res_s2_patch = db_client.patch(
        f"/students/me/admission-targets/{s1_target_id}",
        headers=s2_headers,
        json={"notes": "Hacked"},
    )
    assert res_s2_patch.status_code == 403


# --------------------------------------------------------------------------
# 5. Database Schema Integrity & Constraints Verification
# --------------------------------------------------------------------------

def test_database_constraints_integrity(
    db_session: Session,
    admission_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    student_user = admission_user_factory(Role.STUDENT, "db_const@example.com")
    prof = student_profile(student_user)

    u1, _, m1, _, _, method_thpt, _ = _seed_admission_catalog(db_session, student_user.id)

    # Test CheckConstraint: year >= 2000
    with pytest.raises(IntegrityError):
        invalid_rule = AdmissionRule(
            university_id=u1.id,
            major_id=m1.id,
            year=1999,  # invalid year < 2000
            method_id=method_thpt.id,
            subject_combination="A00",
            requirements={},
        )
        db_session.add(invalid_rule)
        db_session.flush()
    db_session.rollback()

    # Test CheckConstraint: priority_order >= 1 on AdmissionTarget
    with pytest.raises(IntegrityError):
        invalid_target = AdmissionTarget(
            student_id=prof.id,
            university_id=u1.id,
            major_id=m1.id,
            target_type=AdmissionTargetType.DREAM,
            target_year=2026,
            priority_order=0,  # invalid priority < 1
        )
        db_session.add(invalid_target)
        db_session.flush()
    db_session.rollback()
