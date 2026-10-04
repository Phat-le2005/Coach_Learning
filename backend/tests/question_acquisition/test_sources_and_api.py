"""Tests for external PDF sources, fetcher security (SSRF/redirects), upload staging, and Admin API."""

from datetime import datetime, timezone
from io import BytesIO
import ipaddress
from pathlib import Path
import socket
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.question_acquisition.fetcher import SafePdfFetcher
from app.question_acquisition.models import (
    QuestionAcquisitionArtifact,
    QuestionAcquisitionDiscoveryMethod,
    QuestionAcquisitionExtractionStatus,
    QuestionAcquisitionPage,
    QuestionAcquisitionRequest,
    QuestionAcquisitionRequestStatus,
    QuestionAcquisitionRightsStatus,
    QuestionAcquisitionSource,
    QuestionAcquisitionSourceArtifact,
    QuestionAcquisitionSourceKind,
    QuestionAcquisitionSourceStatus,
    QuestionAcquisitionStrategy,
)
from app.question_acquisition.policy import QuestionAcquisitionPolicy
from app.question_acquisition.schemas import RegisterSourceRequest
from app.question_acquisition.service import QuestionAcquisitionService
from app.question_supply.models import (
    QuestionSupplyGap,
    QuestionSupplyObservationSourceKind,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.question_supply.service import (
    QuestionSupplyGapService,
    QuestionSupplyRequirement,
)
from app.questions.models import Question, QuestionStatus
from app.users.models import Role, User
from tests.practice.conftest import (
    PracticeContent,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)
from tests.question_supply.test_sufficiency import _archive_questions, _make_question


def _build_test_pdf(pages_text: list[str]) -> bytes:
    """Construct a minimal valid PDF byte sequence containing extractable text on each page."""
    num_pages = len(pages_text)
    obj_offsets: dict[int, int] = {}
    lines: list[str] = ["%PDF-1.4"]

    def add_obj(obj_id: int, content: str) -> None:
        offset = sum(len(line.encode("latin1")) + 1 for line in lines)
        obj_offsets[obj_id] = offset
        lines.append(f"{obj_id} 0 obj")
        lines.append(content)
        lines.append("endobj")

    kids = " ".join(f"{3 + i * 3} 0 R" for i in range(num_pages))
    add_obj(1, "<< /Type /Catalog /Pages 2 0 R >>")
    add_obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>")

    for i, text in enumerate(pages_text):
        page_id = 3 + i * 3
        contents_id = 4 + i * 3
        font_id = 5 + i * 3
        stream_data = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET"
        add_obj(
            page_id,
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {contents_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>",
        )
        add_obj(
            contents_id,
            f"<< /Length {len(stream_data)} >>\nstream\n{stream_data}\nendstream",
        )
        add_obj(font_id, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    xref_offset = sum(len(line.encode("latin1")) + 1 for line in lines)
    total_objs = 2 + num_pages * 3 + 1
    lines.append("xref")
    lines.append(f"0 {total_objs}")
    lines.append("0000000000 65535 f ")
    for obj_id in range(1, total_objs):
        off = obj_offsets[obj_id]
        lines.append(f"{off:010d} 00000 n ")
    lines.append("trailer")
    lines.append(f"<< /Size {total_objs} /Root 1 0 R >>")
    lines.append("startxref")
    lines.append(str(xref_offset))
    lines.append("%%EOF")
    return "\n".join(lines).encode("latin1")


def _create_test_gap_and_request(
    db_session: Session, practice_content: PracticeContent
) -> tuple[QuestionSupplyGap, QuestionAcquisitionRequest]:
    """Helper to produce a real QuestionSupplyGap and planned QuestionAcquisitionRequest."""
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        preferred_count=4,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
    )
    assert gap is not None
    acq_req = acq_svc.plan_or_get_active_request(gap.id, commit=True)
    return gap, acq_req


# ==============================================================================
# SECTION 81: URL Normalization & Registration Deduplication
# ==============================================================================


def test_url_normalization_rules() -> None:
    # Scheme and host lowercasing, port removal for default ports, fragment removal
    norm, hash1 = QuestionAcquisitionPolicy.normalize_url(
        "HTTP://EXAMPLE.COM:80/path/to/doc.pdf?version=2#page=1"
    )
    assert norm == "http://example.com/path/to/doc.pdf?version=2"
    assert len(hash1) == 64

    norm_https, hash2 = QuestionAcquisitionPolicy.normalize_url(
        "HTTPS://DOCS.GOV.VN:443/exams/2026/test.pdf#section"
    )
    assert norm_https == "https://docs.gov.vn/exams/2026/test.pdf"

    # Preserves non-default ports
    norm_custom, _ = QuestionAcquisitionPolicy.normalize_url(
        "https://archive.org:8443/math.pdf"
    )
    assert norm_custom == "https://archive.org:8443/math.pdf"

    # Reject non-http(s) schemes
    with pytest.raises(ApplicationError) as exc_scheme:
        QuestionAcquisitionPolicy.normalize_url("ftp://example.com/math.pdf")
    assert exc_scheme.value.code == "QUESTION_ACQUISITION_INVALID_SCHEME"

    # Reject embedded credentials
    with pytest.raises(ApplicationError) as exc_creds:
        QuestionAcquisitionPolicy.normalize_url("https://admin:secret@example.com/math.pdf")
    assert exc_creds.value.code == "QUESTION_ACQUISITION_CREDENTIALS_DISALLOWED"


def test_source_registration_provenance_and_deduplication(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    # 1. Provenance note is mandatory
    with pytest.raises(ApplicationError) as exc_prov:
        acq_svc.register_source(
            acq_req.id,
            RegisterSourceRequest(
                source_kind=QuestionAcquisitionSourceKind.PDF_URL,
                url="https://example.edu.vn/doc.pdf",
                provenance_note="   ",
            ),
        )
    assert exc_prov.value.code == "QUESTION_ACQUISITION_PROVENANCE_REQUIRED"

    # 2. Register first time
    source1 = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://example.edu.vn/doc.pdf#page=1",
            provenance_note="Downloaded from National Education Archive",
            title="Grade 10 Math Review",
        ),
    )
    assert source1.id is not None
    assert source1.normalized_url == "https://example.edu.vn/doc.pdf"
    assert source1.rights_status == QuestionAcquisitionRightsStatus.REVIEW_REQUIRED

    # 3. Registering exact same URL under same request is idempotent (returns existing)
    source2 = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://example.edu.vn/doc.pdf#different-hash",
            provenance_note="Duplicate registration attempt",
        ),
    )
    assert source2.id == source1.id

    # Verify database has exactly 1 source row for this request
    count = db_session.scalar(
        select(func.count(QuestionAcquisitionSource.id)).where(
            QuestionAcquisitionSource.request_id == acq_req.id
        )
    )
    assert count == 1


# ==============================================================================
# SECTION 82: Fetch Disabled by Default Without Allowlist
# ==============================================================================


def test_fetch_disabled_without_allowlist() -> None:
    fetcher = SafePdfFetcher(allowed_domains="")
    with pytest.raises(ApplicationError) as exc:
        fetcher.fetch_pdf("https://example.com/math.pdf")
    assert exc.value.code == "QUESTION_ACQUISITION_FETCH_DISABLED"


# ==============================================================================
# SECTION 83: SSRF and Private Network Blocking
# ==============================================================================


@pytest.mark.parametrize(
    "ssrf_target",
    [
        "http://127.0.0.1/test.pdf",
        "http://127.0.0.1:8080/test.pdf",
        "http://localhost/test.pdf",
        "http://internal.local/test.pdf",
        "http://10.0.0.1/test.pdf",
        "http://172.16.0.5/test.pdf",
        "http://192.168.1.1/test.pdf",
        "http://169.254.169.254/latest/meta-data",  # Cloud metadata IP
        "http://[::1]/test.pdf",
    ],
)
def test_ssrf_and_private_network_blocking(ssrf_target: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # Allow all domains in the test fetcher to isolate the SSRF check
    fetcher = SafePdfFetcher(allowed_domains="*")

    # Mock DNS resolution for domain names
    def mock_getaddrinfo(host, port, *args, **kwargs):
        if host in {"localhost", "internal.local"}:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]
        try:
            ip = ipaddress.ip_address(host)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (str(ip), port))]
        except ValueError:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    with pytest.raises(ApplicationError) as exc:
        fetcher.validate_url_safety(ssrf_target)
    assert exc.value.code == "QUESTION_ACQUISITION_SSRF_BLOCKED"


# ==============================================================================
# SECTION 84: Domain Allowlist Enforcement
# ==============================================================================


def test_domain_allowlist_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher = SafePdfFetcher(allowed_domains="trusted.edu.vn, *.moet.gov.vn")

    # Mock public IP resolution
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    # Allowed exact domain
    valid_exact = fetcher.validate_url_safety("https://trusted.edu.vn/math.pdf")
    assert valid_exact == "https://trusted.edu.vn/math.pdf"

    # Allowed wildcard subdomain
    valid_sub = fetcher.validate_url_safety("https://exam.moet.gov.vn/math.pdf")
    assert valid_sub == "https://exam.moet.gov.vn/math.pdf"

    # Disallowed domain
    with pytest.raises(ApplicationError) as exc_disallowed:
        fetcher.validate_url_safety("https://malicious.org/math.pdf")
    assert exc_disallowed.value.code == "QUESTION_ACQUISITION_DOMAIN_NOT_ALLOWED"


# ==============================================================================
# SECTION 85: Redirect Safety
# ==============================================================================


def test_redirect_safety_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    # Public DNS mock
    def mock_getaddrinfo(host, port, *args, **kwargs):
        if host == "169.254.169.254":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    # 1. Safe redirect within allowlist
    valid_pdf = _build_test_pdf(["Redirected Math Test"])

    def safe_redirect_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "https://trusted.edu.vn/final.pdf"})
        if request.url.path == "/final.pdf":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/pdf"},
                content=valid_pdf,
            )
        return httpx.Response(404)

    fetcher_safe = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(safe_redirect_handler),
    )
    result = fetcher_safe.fetch_pdf("https://trusted.edu.vn/start")
    assert result.file_size_bytes == len(valid_pdf)
    assert result.temp_file_path.exists()
    result.temp_file_path.unlink()

    # 2. Redirect to SSRF cloud metadata is blocked
    def ssrf_redirect_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data"})

    fetcher_ssrf = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(ssrf_redirect_handler),
    )
    with pytest.raises(ApplicationError) as exc_ssrf:
        fetcher_ssrf.fetch_pdf("https://trusted.edu.vn/start")
    assert exc_ssrf.value.code == "QUESTION_ACQUISITION_DOMAIN_NOT_ALLOWED"

    # 3. Redirect to outside domain is blocked
    def external_redirect_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://evil.com/payload.pdf"})

    fetcher_ext = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(external_redirect_handler),
    )
    with pytest.raises(ApplicationError) as exc_ext:
        fetcher_ext.fetch_pdf("https://trusted.edu.vn/start")
    assert exc_ext.value.code == "QUESTION_ACQUISITION_DOMAIN_NOT_ALLOWED"

    # 4. Redirect loop (> 3 redirects)
    def loop_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://trusted.edu.vn/loop"})

    fetcher_loop = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(loop_handler),
    )
    with pytest.raises(ApplicationError) as exc_loop:
        fetcher_loop.fetch_pdf("https://trusted.edu.vn/loop")
    assert exc_loop.value.code == "QUESTION_ACQUISITION_TOO_MANY_REDIRECTS"


# ==============================================================================
# SECTION 86 & 87: PDF Validation & HTML Rejection
# ==============================================================================


def test_fetch_rejects_html_and_non_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    # 1. HTML Content-Type rejection
    def html_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=b"<!DOCTYPE html><html><body>Error 404 Not Found</body></html>",
        )

    fetcher_html = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(html_handler),
    )
    with pytest.raises(ApplicationError) as exc_html:
        fetcher_html.fetch_pdf("https://trusted.edu.vn/doc")
    assert exc_html.value.code == "QUESTION_ACQUISITION_NOT_PDF"

    # 2. Binary content missing %PDF- magic header
    def non_pdf_binary_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/octet-stream"},
            content=b"THIS IS NOT A VALID PDF FILE HEADER",
        )

    fetcher_bin = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(non_pdf_binary_handler),
    )
    with pytest.raises(ApplicationError) as exc_bin:
        fetcher_bin.fetch_pdf("https://trusted.edu.vn/doc")
    assert exc_bin.value.code == "QUESTION_ACQUISITION_NOT_PDF"


# ==============================================================================
# SECTION 88: File Size Limit Rejection
# ==============================================================================


def test_file_size_limit_rejection(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    practice_content: PracticeContent,
) -> None:
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    max_test_bytes = 1024  # 1 KB limit for testing

    # 1. Fetcher rejects response stream exceeding max bytes
    large_pdf_chunk = b"%PDF-1.4\n" + b"A" * 2048

    def large_pdf_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=large_pdf_chunk,
        )

    fetcher = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        max_bytes=max_test_bytes,
        transport=httpx.MockTransport(large_pdf_handler),
    )
    with pytest.raises(ApplicationError) as exc:
        fetcher.fetch_pdf("https://trusted.edu.vn/large.pdf")
    assert exc.value.code == "QUESTION_ACQUISITION_FILE_TOO_LARGE"

    # 2. Manual upload rejects bytes exceeding max bytes
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)
    acq_svc.max_bytes = max_test_bytes

    with pytest.raises(ApplicationError) as exc_up:
        acq_svc.upload_artifact(
            acq_req.id,
            file_bytes=large_pdf_chunk,
            provenance_note="Test upload too large",
        )
    assert exc_up.value.code == "QUESTION_ACQUISITION_FILE_TOO_LARGE"


# ==============================================================================
# SECTION 89: Artifact Deduplication (Identical SHA-256)
# ==============================================================================


def test_artifact_deduplication(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _, req1 = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    pdf_bytes = _build_test_pdf(["Common Material Question 1"])

    # First upload under req1
    src1, art1 = acq_svc.upload_artifact(
        req1.id,
        file_bytes=pdf_bytes,
        provenance_note="First provenance upload",
        title="Math Exam 2026",
    )
    assert art1.id is not None

    # Query initial artifact count
    initial_artifact_count = db_session.scalar(
        select(func.count(QuestionAcquisitionArtifact.id))
    )

    # Second upload of the exact same bytes under req1 (or another request)
    src2, art2 = acq_svc.upload_artifact(
        req1.id,
        file_bytes=pdf_bytes,
        provenance_note="Second provenance upload with same PDF bytes",
        title="Math Exam 2026 Copy",
    )

    # Artifact MUST be reused!
    assert art2.id == art1.id
    assert art2.sha256 == art1.sha256

    # Distinct source rows created
    assert src1.id != src2.id

    # Total artifact rows did NOT increase
    final_artifact_count = db_session.scalar(
        select(func.count(QuestionAcquisitionArtifact.id))
    )
    assert final_artifact_count == initial_artifact_count

    # Both sources are linked to the same artifact
    links = db_session.scalars(
        select(QuestionAcquisitionSourceArtifact).where(
            QuestionAcquisitionSourceArtifact.artifact_id == art1.id
        )
    ).all()
    assert len(links) == 2


# ==============================================================================
# SECTION 90 & 92: Manual Upload, Text Extraction & READY_FOR_REVIEW Transition
# ==============================================================================


def test_manual_pdf_upload_flow_and_extraction(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    assert acq_req.status in {
        QuestionAcquisitionRequestStatus.PLANNED,
        QuestionAcquisitionRequestStatus.AWAITING_SOURCE,
    }

    page1_text = "Cau 1: Tinh gia tri bieu thuc x + 2 = 5"
    page2_text = "Cau 2: Cho tam giac ABC vuong tai A"
    pdf_bytes = _build_test_pdf([page1_text, page2_text])

    source, artifact = acq_svc.upload_artifact(
        acq_req.id,
        file_bytes=pdf_bytes,
        provenance_note="De thi thu toan THPT 2026",
        title="Toan 10 Hoc ky 1",
        publisher="So GD-DT",
        source_year=2026,
    )

    # 1. Source verification
    assert source.source_kind == QuestionAcquisitionSourceKind.MANUAL_PDF_UPLOAD
    assert source.status == QuestionAcquisitionSourceStatus.FETCHED
    assert source.rights_status == QuestionAcquisitionRightsStatus.REVIEW_REQUIRED

    # 2. Artifact & page text extraction verification
    assert artifact.extraction_status == QuestionAcquisitionExtractionStatus.COMPLETE
    assert artifact.page_count == 2
    assert artifact.file_size_bytes == len(pdf_bytes)

    extracted_pages = db_session.scalars(
        select(QuestionAcquisitionPage)
        .where(QuestionAcquisitionPage.artifact_id == artifact.id)
        .order_by(QuestionAcquisitionPage.page_number)
    ).all()
    assert len(extracted_pages) == 2
    assert extracted_pages[0].page_number == 1
    assert extracted_pages[0].text == page1_text
    assert extracted_pages[0].char_count == len(page1_text)
    assert len(extracted_pages[0].text_sha256) == 64

    assert extracted_pages[1].page_number == 2
    assert extracted_pages[1].text == page2_text

    # 3. Request status transitioned to READY_FOR_REVIEW
    reloaded_req = acq_svc.get_request(acq_req.id)
    assert reloaded_req is not None
    assert reloaded_req.status == QuestionAcquisitionRequestStatus.READY_FOR_REVIEW


# ==============================================================================
# SECTION 93: Broken PDF Isolation (No Crash)
# ==============================================================================


def test_broken_pdf_isolation(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    # Valid magic header %PDF- but corrupted binary body
    corrupted_pdf = b"%PDF-1.4\nBROKEN_CORRUPTED_STREAM_GARBAGE_NO_XREF"

    source, artifact = acq_svc.upload_artifact(
        acq_req.id,
        file_bytes=corrupted_pdf,
        provenance_note="Corrupted scan file",
    )

    # Ingestion does NOT crash; extraction_status is recorded as FAILED
    assert artifact.extraction_status == QuestionAcquisitionExtractionStatus.FAILED
    assert artifact.page_count is None

    # Request status should NOT transition to READY_FOR_REVIEW
    reloaded_req = acq_svc.get_request(acq_req.id)
    assert reloaded_req is not None
    assert reloaded_req.status != QuestionAcquisitionRequestStatus.READY_FOR_REVIEW


# ==============================================================================
# SECTION 94: Zero Question Table Side-Effects Assertion
# ==============================================================================


def test_zero_question_table_side_effects(
    db_session: Session, practice_content: PracticeContent
) -> None:
    """Critical boundary invariant: ACQ-002 must NEVER create or alter Question rows."""
    _archive_questions(db_session)
    q_count_before = db_session.scalar(select(func.count(Question.id)))
    approved_count_before = db_session.scalar(
        select(func.count(Question.id)).where(Question.status == QuestionStatus.APPROVED)
    )

    # Perform entire acquisition workflow
    gap_svc = QuestionSupplyGapService(db_session)
    acq_svc = QuestionAcquisitionService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        preferred_count=4,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
    )
    assert gap is not None
    acq_req = acq_svc.plan_or_get_active_request(gap.id, commit=True)

    pdf_bytes = _build_test_pdf(["Geometry problem 1"])
    src, art = acq_svc.upload_artifact(
        acq_req.id,
        file_bytes=pdf_bytes,
        provenance_note="Strict invariant verification test",
    )
    acq_svc.block_source(src.id, reason="Copyright review block")
    acq_svc.cancel_request(acq_req.id, reason="Completed test cycle")
    db_session.commit()

    # Query Question counts after
    q_count_after = db_session.scalar(select(func.count(Question.id)))
    approved_count_after = db_session.scalar(
        select(func.count(Question.id)).where(Question.status == QuestionStatus.APPROVED)
    )

    assert q_count_after == q_count_before, "ACQ-002 must not add Question rows!"
    assert approved_count_after == approved_count_before, "ACQ-002 must not alter Question statuses!"


# ==============================================================================
# SECTION 95: Rights Boundary Default REVIEW_REQUIRED & Blocking
# ==============================================================================


def test_rights_boundary_and_source_blocking(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    src = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://example.edu.vn/licensed.pdf",
            provenance_note="Educational licensing under review",
        ),
    )
    assert src.rights_status == QuestionAcquisitionRightsStatus.REVIEW_REQUIRED

    # Admin blocks source
    blocked = acq_svc.block_source(src.id, reason="Publisher DMCA takedown notice")
    assert blocked.rights_status == QuestionAcquisitionRightsStatus.BLOCKED
    assert blocked.status == QuestionAcquisitionSourceStatus.BLOCKED
    assert blocked.failure_code == "MANUALLY_BLOCKED"

    # Attempting to fetch a blocked source must fail
    with pytest.raises(ApplicationError) as exc_blocked:
        acq_svc.fetch_source(src.id)
    assert exc_blocked.value.code == "QUESTION_ACQUISITION_SOURCE_BLOCKED"


# ==============================================================================
# SECTION 96: Admin Authorization & API Endpoints
# ==============================================================================


def test_admin_authorization_enforced(
    db_client: TestClient,
    db_session: Session,
    practice_content: PracticeContent,
    practice_user_factory,
    practice_bearer,
) -> None:
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)

    admin_user = practice_user_factory(Role.ADMIN, "admin_acq@test.com")
    teacher_user = practice_user_factory(Role.TEACHER, "teacher_acq@test.com")
    student_user = practice_user_factory(Role.STUDENT, "student_acq@test.com")

    admin_headers = practice_bearer(admin_user)
    teacher_headers = practice_bearer(teacher_user)
    student_headers = practice_bearer(student_user)

    url = f"/question-acquisition/requests/{acq_req.id}"

    # 1. Unauthenticated -> 401
    resp_unauth = db_client.get(url)
    assert resp_unauth.status_code == 401

    # 2. Student -> 403 Forbidden
    resp_student = db_client.get(url, headers=student_headers)
    assert resp_student.status_code == 403

    # 3. Teacher -> 403 Forbidden
    resp_teacher = db_client.get(url, headers=teacher_headers)
    assert resp_teacher.status_code == 403

    # 4. Admin -> 200 OK
    resp_admin = db_client.get(url, headers=admin_headers)
    assert resp_admin.status_code == 200
    data = resp_admin.json()
    assert data["id"] == str(acq_req.id)
    assert "existing_candidates" in data
    assert "sources" in data
    assert "artifacts" in data


def test_api_manual_upload_and_block_flow(
    db_client: TestClient,
    db_session: Session,
    practice_content: PracticeContent,
    practice_user_factory,
    practice_bearer,
) -> None:
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    admin_user = practice_user_factory(Role.ADMIN, "admin_upload_flow@test.com")
    headers = practice_bearer(admin_user)

    pdf_bytes = _build_test_pdf(["De kiem tra 15 phut Dai so"])

    # 1. Upload PDF artifact
    resp_upload = db_client.post(
        f"/question-acquisition/requests/{acq_req.id}/artifacts/upload",
        headers=headers,
        data={
            "provenance_note": "Bien soan boi to Toan Truong Chuyen",
            "title": "Kiem tra 15 phut",
        },
        files={"file": ("test_exam.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp_upload.status_code == 200
    art_data = resp_upload.json()
    assert art_data["extraction_status"] == "COMPLETE"
    assert art_data["page_count"] == 1

    # 2. Get request detail -> verify staged & READY_FOR_REVIEW
    resp_detail = db_client.get(
        f"/question-acquisition/requests/{acq_req.id}",
        headers=headers,
    )
    assert resp_detail.status_code == 200
    detail_data = resp_detail.json()
    assert detail_data["status"] == "READY_FOR_REVIEW"
    assert len(detail_data["sources"]) == 1
    source_id = detail_data["sources"][0]["id"]

    # 3. Block source via API
    resp_block = db_client.post(
        f"/question-acquisition/sources/{source_id}/block",
        headers=headers,
        json={"reason": "Contains copyrighted proprietary questions"},
    )
    assert resp_block.status_code == 200
    block_data = resp_block.json()
    assert block_data["rights_status"] == "BLOCKED"
    assert block_data["status"] == "BLOCKED"


def test_gap_to_acquisition_router_endpoint(
    db_client: TestClient,
    db_session: Session,
    practice_content: PracticeContent,
    practice_user_factory,
    practice_bearer,
) -> None:
    _archive_questions(db_session)
    gap_svc = QuestionSupplyGapService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        preferred_count=4,
    )
    _, gap = gap_svc.assess_and_record(
        requirement=req,
        source_kind=QuestionSupplyObservationSourceKind.ROOT_CAUSE_VERIFICATION,
        source_entity_id=uuid4(),
    )
    assert gap is not None

    admin_user = practice_user_factory(Role.ADMIN, "admin_gap_acq@test.com")
    student_user = practice_user_factory(Role.STUDENT, "student_gap_acq@test.com")

    # Student cannot trigger acquisition for gap -> 403
    resp_student = db_client.post(
        f"/question-supply/gaps/{gap.id}/acquisition",
        headers=practice_bearer(student_user),
    )
    assert resp_student.status_code == 403

    # Admin triggers acquisition -> 200
    resp_admin = db_client.post(
        f"/question-supply/gaps/{gap.id}/acquisition",
        headers=practice_bearer(admin_user),
    )
    assert resp_admin.status_code == 200
    data = resp_admin.json()
    assert data["gap_id"] == str(gap.id)
    assert data["status"] in {"PLANNED", "AWAITING_SOURCE"}
