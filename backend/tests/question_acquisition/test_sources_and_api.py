"""Tests for external PDF sources, fetcher security (SSRF/redirects), upload staging, and Admin API."""

from datetime import datetime, timezone
from io import BytesIO
import ipaddress
from pathlib import Path
import socket
from uuid import UUID, uuid4

import httpcore
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import ApplicationError
from app.question_acquisition.fetcher import (
    FetchResult,
    PinnedResponseStream,
    PinnedSyncBackend,
    PinnedTransport,
    SafePdfFetcher,
)
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
from app.question_acquisition.policy import (
    QuestionAcquisitionPolicy,
    StreamIngestValidator,
)
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


def test_bare_wildcard_domain_disallowed() -> None:
    with pytest.raises(ValueError, match="Bare wildcard"):
        SafePdfFetcher(allowed_domains="*")


@pytest.mark.parametrize(
    "ssrf_target, expected_code",
    [
        ("http://127.0.0.1/test.pdf", "QUESTION_ACQUISITION_IP_LITERAL_DISALLOWED"),
        ("http://127.0.0.1:8080/test.pdf", "QUESTION_ACQUISITION_IP_LITERAL_DISALLOWED"),
        ("http://localhost/test.pdf", "QUESTION_ACQUISITION_SSRF_BLOCKED"),
        ("http://internal.local/test.pdf", "QUESTION_ACQUISITION_SSRF_BLOCKED"),
        ("http://10.0.0.1/test.pdf", "QUESTION_ACQUISITION_IP_LITERAL_DISALLOWED"),
        ("http://172.16.0.5/test.pdf", "QUESTION_ACQUISITION_IP_LITERAL_DISALLOWED"),
        ("http://192.168.1.1/test.pdf", "QUESTION_ACQUISITION_IP_LITERAL_DISALLOWED"),
        ("http://169.254.169.254/latest/meta-data", "QUESTION_ACQUISITION_IP_LITERAL_DISALLOWED"),
        ("http://[::1]/test.pdf", "QUESTION_ACQUISITION_IP_LITERAL_DISALLOWED"),
    ],
)
def test_ssrf_and_private_network_blocking(
    ssrf_target: str, expected_code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Allow test hosts in domain allowlist to isolate SSRF / IP literal checks
    fetcher = SafePdfFetcher(allowed_domains="localhost, internal.local, evil.com")

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
    assert exc.value.code == expected_code


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
    assert valid_exact.url == "https://trusted.edu.vn/math.pdf"
    assert valid_exact.hostname == "trusted.edu.vn"

    # Allowed wildcard subdomain
    valid_sub = fetcher.validate_url_safety("https://exam.moet.gov.vn/math.pdf")
    assert valid_sub.url == "https://exam.moet.gov.vn/math.pdf"
    assert valid_sub.hostname == "exam.moet.gov.vn"

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
    assert exc_ssrf.value.code in {
        "QUESTION_ACQUISITION_IP_LITERAL_DISALLOWED",
        "QUESTION_ACQUISITION_DOMAIN_NOT_ALLOWED",
    }

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


# ==============================================================================
# SECTION 97: Hardening Tests (ACQ-002 Invariants)
# ==============================================================================


def test_zero_text_pdf_extraction_fails(
    db_session: Session, practice_content: PracticeContent
) -> None:
    """PDF with valid format but no extractable text must fail extraction with OCR not enabled message."""
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    # Build PDF with empty text on pages
    zero_text_pdf = _build_test_pdf(["", ""])
    source, artifact = acq_svc.upload_artifact(
        acq_req.id,
        file_bytes=zero_text_pdf,
        provenance_note="Zero text scanned exam without OCR",
    )

    assert artifact.extraction_status == QuestionAcquisitionExtractionStatus.FAILED
    assert source.status == QuestionAcquisitionSourceStatus.FAILED
    assert source.failure_code == "QUESTION_ACQUISITION_PDF_EXTRACTION_FAILED"
    assert "no extractable text" in (source.failure_detail or "").lower()

    # Request status must remain AWAITING_SOURCE because no usable artifact exists
    reloaded_req = acq_svc.get_request(acq_req.id)
    assert reloaded_req is not None
    assert reloaded_req.status == QuestionAcquisitionRequestStatus.AWAITING_SOURCE


def test_mixed_dns_answers_ssrf_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """If DNS returns any private/restricted IP alongside public IPs, fetch must be rejected."""
    fetcher = SafePdfFetcher(allowed_domains="dns-rebind.edu.vn")

    # Mock DNS returning both public IP and private 10.0.0.1
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    with pytest.raises(ApplicationError) as exc:
        fetcher.validate_url_safety("https://dns-rebind.edu.vn/doc.pdf")
    assert exc.value.code == "QUESTION_ACQUISITION_SSRF_BLOCKED"


def test_fetch_failure_persists_in_database(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network fetch failures must persist status=FAILED, failure_code, and detail to DB before raising."""
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"Internal Server Error")

    fetcher = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(failing_handler),
    )
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session, fetcher=fetcher)

    source = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/server_error.pdf",
            provenance_note="Server failure test",
        ),
    )

    with pytest.raises(ApplicationError) as exc:
        acq_svc.fetch_source(source.id, commit=True)
    assert exc.value.code == "QUESTION_ACQUISITION_FETCH_FAILED"

    # Reload from DB and verify failure persisted
    db_session.expire_all()
    reloaded_source = db_session.get(QuestionAcquisitionSource, source.id)
    assert reloaded_source is not None
    assert reloaded_source.status == QuestionAcquisitionSourceStatus.FAILED
    assert reloaded_source.failure_code == "QUESTION_ACQUISITION_FETCH_FAILED"
    assert "500" in (reloaded_source.failure_detail or "")


def test_retry_failed_source_success(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retrying a previously FAILED source clears failure markers and updates status to FETCHED."""
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    valid_pdf = _build_test_pdf(["Retried Math Test Exam"])
    attempt_count = 0

    def retryable_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            return httpx.Response(503, content=b"Service Temporarily Unavailable")
        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=valid_pdf,
        )

    fetcher = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(retryable_handler),
    )
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session, fetcher=fetcher)

    source = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/intermittent.pdf",
            provenance_note="Intermittent server retry test",
        ),
    )

    # First attempt fails
    with pytest.raises(ApplicationError):
        acq_svc.fetch_source(source.id, commit=True)

    reloaded_failed = db_session.get(QuestionAcquisitionSource, source.id)
    assert reloaded_failed is not None
    assert reloaded_failed.status == QuestionAcquisitionSourceStatus.FAILED

    # Second attempt succeeds (retry)
    artifact = acq_svc.fetch_source(source.id, commit=True)
    assert artifact is not None
    assert artifact.extraction_status == QuestionAcquisitionExtractionStatus.COMPLETE

    reloaded_success = db_session.get(QuestionAcquisitionSource, source.id)
    assert reloaded_success is not None
    assert reloaded_success.status == QuestionAcquisitionSourceStatus.FETCHED
    assert reloaded_success.failure_code is None
    assert reloaded_success.failure_detail is None

    # Check request promoted to READY_FOR_REVIEW
    reloaded_req = acq_svc.get_request(acq_req.id)
    assert reloaded_req is not None
    assert reloaded_req.status == QuestionAcquisitionRequestStatus.READY_FOR_REVIEW


def test_blocking_source_demotes_request(
    db_session: Session, practice_content: PracticeContent
) -> None:
    """When the only usable source in a request is blocked, the request demotes from READY_FOR_REVIEW to AWAITING_SOURCE."""
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    pdf_bytes = _build_test_pdf(["Calculus 1 Midterm"])
    source, artifact = acq_svc.upload_artifact(
        acq_req.id,
        file_bytes=pdf_bytes,
        provenance_note="Single usable source test",
    )

    reloaded_req = acq_svc.get_request(acq_req.id)
    assert reloaded_req is not None
    assert reloaded_req.status == QuestionAcquisitionRequestStatus.READY_FOR_REVIEW

    # Block the only usable source
    acq_svc.block_source(source.id, reason="Legal infringement challenge", commit=True)

    reloaded_req_blocked = acq_svc.get_request(acq_req.id)
    assert reloaded_req_blocked is not None
    assert reloaded_req_blocked.status == QuestionAcquisitionRequestStatus.AWAITING_SOURCE


def test_stream_upload_api_size_limit(
    db_client: TestClient,
    db_session: Session,
    practice_content: PracticeContent,
    practice_user_factory,
    practice_bearer,
) -> None:
    """Streaming upload via API rejects files exceeding max size and cleans up temp files."""
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    admin_user = practice_user_factory(Role.ADMIN, "admin_stream_size@test.com")
    headers = practice_bearer(admin_user)

    from app.core.config import get_settings
    orig_max = get_settings().question_acquisition_max_bytes
    get_settings().question_acquisition_max_bytes = 512

    try:
        large_pdf = b"%PDF-1.4\n" + b"X" * 1024
        resp = db_client.post(
            f"/question-acquisition/requests/{acq_req.id}/artifacts/upload",
            headers=headers,
            data={"provenance_note": "Oversized upload test"},
            files={"file": ("too_large.pdf", large_pdf, "application/pdf")},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "QUESTION_ACQUISITION_FILE_TOO_LARGE"
    finally:
        get_settings().question_acquisition_max_bytes = orig_max


def test_concurrent_source_registration_race(
    db_session: Session, practice_content: PracticeContent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a concurrent transaction registers the same (request_id, url_hash), savepoint recovers and returns winner."""
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    # First register succeeds normally
    s1 = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/race.pdf",
            provenance_note="Race test provenance",
        ),
        commit=True,
    )

    orig_scalar = db_session.scalar
    calls = 0

    def mock_scalar(stmt, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            # Pre-insert check pretends source does not exist
            return None
        # Subsequent check in IntegrityError recovery finds s1
        return orig_scalar(stmt, *args, **kwargs)

    monkeypatch.setattr(db_session, "scalar", mock_scalar)

    s2 = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/race.pdf",
            provenance_note="Race duplicate attempt",
        ),
        commit=True,
    )
    assert s2.id == s1.id


def test_concurrent_artifact_ingest_race(
    db_session: Session, practice_content: PracticeContent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When another thread inserts the exact same sha256 artifact concurrently, nested transaction recovers."""
    import tempfile
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    pdf_bytes = _build_test_pdf(["Concurrency test artifact"])
    s1, art1 = acq_svc.upload_artifact(
        acq_req.id,
        file_bytes=pdf_bytes,
        provenance_note="First artifact upload",
    )

    s2 = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.MANUAL_PDF_UPLOAD,
            provenance_note="Second source",
        ),
    )

    orig_scalar = db_session.scalar
    calls = 0

    def mock_scalar(stmt, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return orig_scalar(stmt, *args, **kwargs)

    monkeypatch.setattr(db_session, "scalar", mock_scalar)

    with tempfile.NamedTemporaryFile(prefix="acq_race_", suffix=".tmp", delete=False) as tf:
        tf.write(pdf_bytes)
        temp_path = Path(tf.name)

    try:
        art2 = acq_svc._ingest_artifact_file(
            source=s2,
            file_path=temp_path,
            sha256=art1.sha256,
            file_size_bytes=len(pdf_bytes),
        )
        assert art2.id == art1.id
        assert art2.sha256 == art1.sha256
    finally:
        temp_path.unlink(missing_ok=True)


# ==============================================================================
# SECTION 98: PinnedTransport & HTTPCore Contract Regression Tests
# ==============================================================================


def test_pinned_transport_adapts_httpx_request_to_httpcore() -> None:
    """PinnedTransport must translate httpx.Request to httpcore.Request with method, url, headers, content, and wrap httpcore.Response."""
    recorded_requests: list[httpcore.Request] = []
    pool_closed = False

    class FakePool:
        def handle_request(self, req: httpcore.Request) -> httpcore.Response:
            recorded_requests.append(req)
            assert isinstance(req, httpcore.Request)
            assert req.method == b"POST"
            assert req.url.scheme == b"https"
            assert req.url.host == b"exam.edu.vn"
            assert req.url.port is None
            assert req.url.target == b"/api/submit?key=val"
            headers_dict = {k.lower(): v for k, v in req.headers}
            assert headers_dict[b"custom-header"] == b"TestValue"
            body = b"".join(list(req.stream))
            assert body == b"hello request body"
            return httpcore.Response(
                status=201,
                headers=[(b"custom-response", b"Success")],
                content=[b"%PDF-1.4\nresponse data"],
            )

        def close(self) -> None:
            nonlocal pool_closed
            pool_closed = True

    fake_pool = FakePool()
    transport = PinnedTransport(
        host_to_ip_map={"exam.edu.vn": "93.184.216.34"},
        pool=fake_pool,
    )

    with httpx.Client(transport=transport) as client:
        resp = client.post(
            "https://exam.edu.vn/api/submit?key=val",
            headers={"Custom-Header": "TestValue"},
            content=b"hello request body",
        )
        assert resp.status_code == 201
        assert resp.headers["custom-response"] == "Success"
        assert resp.content == b"%PDF-1.4\nresponse data"

    assert len(recorded_requests) == 1
    transport.close()
    assert pool_closed is True


def test_pinned_sync_backend_connect_tcp_pins_ip() -> None:
    """PinnedSyncBackend.connect_tcp must translate mapped hostname to pinned IP and leave unmapped intact."""
    backend = PinnedSyncBackend({"exam.edu.vn": "93.184.216.34"})
    captured_calls: list[tuple[str, int]] = []

    def mock_super_connect(self, host: str, port: int, **kwargs):
        captured_calls.append((host, port))
        return "fake_stream"

    orig_connect = httpcore.SyncBackend.connect_tcp
    httpcore.SyncBackend.connect_tcp = mock_super_connect
    try:
        res1 = backend.connect_tcp("exam.edu.vn", 443)
        assert res1 == "fake_stream"
        assert captured_calls[-1] == ("93.184.216.34", 443)

        res2 = backend.connect_tcp("unmapped.org", 80)
        assert res2 == "fake_stream"
        assert captured_calls[-1] == ("unmapped.org", 80)
    finally:
        httpcore.SyncBackend.connect_tcp = orig_connect


def test_pinned_response_stream_close_propagates() -> None:
    """PinnedResponseStream must close the underlying HTTPCore stream upon response close."""
    stream_closed = False

    class ClosableByteIterable:
        def __iter__(self):
            yield b"%PDF-1.4\nchunk"

        def close(self):
            nonlocal stream_closed
            stream_closed = True

    class FakePool:
        def handle_request(self, req: httpcore.Request) -> httpcore.Response:
            return httpcore.Response(status=200, content=ClosableByteIterable())

        def close(self):
            pass

    transport = PinnedTransport({"example.com": "1.2.3.4"}, pool=FakePool())
    with httpx.Client(transport=transport) as client:
        with client.stream("GET", "https://example.com/doc.pdf") as resp:
            chunk = next(resp.iter_bytes())
            assert chunk == b"%PDF-1.4\nchunk"
            assert stream_closed is False

    assert stream_closed is True


# ==============================================================================
# SECTION 99: Source & Artifact Retry Semantics Regression Tests
# ==============================================================================


def test_failed_extraction_artifact_does_not_short_circuit_retry(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a source has a linked artifact that FAILED extraction, retry must fetch again rather than short-circuiting."""
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    zero_text_pdf = _build_test_pdf(["", ""])
    valid_pdf = _build_test_pdf(["Successfully recovered test question 1"])

    fetch_call_count = 0

    def retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal fetch_call_count
        fetch_call_count += 1
        if fetch_call_count == 1:
            return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=zero_text_pdf)
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=valid_pdf)

    fetcher = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(retry_handler),
    )
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session, fetcher=fetcher)

    source = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/ocr_needed.pdf",
            provenance_note="Scanned PDF retry verification",
        ),
    )

    # 1. First fetch attempt downloads zero-text PDF -> extraction FAILED
    art1 = acq_svc.fetch_source(source.id, commit=True)
    assert art1.extraction_status == QuestionAcquisitionExtractionStatus.FAILED
    assert source.status == QuestionAcquisitionSourceStatus.FAILED
    assert source.failure_code == "QUESTION_ACQUISITION_PDF_EXTRACTION_FAILED"
    assert fetch_call_count == 1

    reloaded_req = acq_svc.get_request(acq_req.id)
    assert reloaded_req is not None
    assert reloaded_req.status == QuestionAcquisitionRequestStatus.AWAITING_SOURCE

    # 2. Second fetch attempt (retry) MUST NOT short-circuit on the failed artifact!
    art2 = acq_svc.fetch_source(source.id, commit=True)
    assert fetch_call_count == 2
    assert art2.id != art1.id
    assert art2.extraction_status == QuestionAcquisitionExtractionStatus.COMPLETE
    assert art2.page_count == 1

    # Reload from DB and verify audit invariants
    db_session.expire_all()
    reloaded_source = db_session.get(QuestionAcquisitionSource, source.id)
    assert reloaded_source is not None
    assert reloaded_source.status == QuestionAcquisitionSourceStatus.FETCHED
    assert reloaded_source.failure_code is None
    assert reloaded_source.failure_detail is None

    # Both artifacts are linked to source for audit trail
    links = db_session.scalars(
        select(QuestionAcquisitionSourceArtifact).where(
            QuestionAcquisitionSourceArtifact.source_id == source.id
        )
    ).all()
    assert len(links) == 2
    linked_artifact_ids = {lnk.artifact_id for lnk in links}
    assert art1.id in linked_artifact_ids
    assert art2.id in linked_artifact_ids

    # Old failed artifact is immutable and preserved
    old_art = db_session.get(QuestionAcquisitionArtifact, art1.id)
    assert old_art is not None
    assert old_art.extraction_status == QuestionAcquisitionExtractionStatus.FAILED

    # Helper get_usable_source_artifact returns the latest usable one
    usable = acq_svc.get_usable_source_artifact(source.id)
    assert usable is not None
    assert usable.id == art2.id

    # Request is now promoted to READY_FOR_REVIEW
    req_promoted = acq_svc.get_request(acq_req.id)
    assert req_promoted is not None
    assert req_promoted.status == QuestionAcquisitionRequestStatus.READY_FOR_REVIEW


def test_retry_same_failed_binary_reuses_failed_artifact_and_remains_failed(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When retry returns the exact same failing binary (same sha256), the failed artifact is reused and source stays FAILED."""
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    zero_text_pdf = _build_test_pdf(["", ""])
    fetch_calls = 0

    def same_failing_handler(request: httpx.Request) -> httpx.Response:
        nonlocal fetch_calls
        fetch_calls += 1
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=zero_text_pdf)

    fetcher = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(same_failing_handler),
    )
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session, fetcher=fetcher)

    source = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/still_broken.pdf",
            provenance_note="Still broken scan retry test",
        ),
    )

    # First fetch attempt
    art1 = acq_svc.fetch_source(source.id, commit=True)
    assert art1.extraction_status == QuestionAcquisitionExtractionStatus.FAILED
    assert fetch_calls == 1

    # Second fetch attempt returns same failing bytes
    art2 = acq_svc.fetch_source(source.id, commit=True)
    assert fetch_calls == 2
    assert art2.id == art1.id  # Reused by sha256 dedupe!

    # No duplicate artifact created in DB
    total_artifacts = db_session.scalar(
        select(func.count(QuestionAcquisitionArtifact.id))
    )
    assert total_artifacts == 1

    reloaded_source = db_session.get(QuestionAcquisitionSource, source.id)
    assert reloaded_source is not None
    assert reloaded_source.status == QuestionAcquisitionSourceStatus.FAILED
    assert reloaded_source.failure_code == "QUESTION_ACQUISITION_PDF_EXTRACTION_FAILED"


def test_fetch_source_success_idempotency_does_not_call_network(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a source is already FETCHED with a usable artifact, fetch_source must short-circuit without calling network."""
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    valid_pdf = _build_test_pdf(["Algebra Chapter 1 Test"])
    fetch_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal fetch_calls
        fetch_calls += 1
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=valid_pdf)

    fetcher = SafePdfFetcher(
        allowed_domains="trusted.edu.vn",
        transport=httpx.MockTransport(handler),
    )
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session, fetcher=fetcher)

    source = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/idempotency_test.pdf",
            provenance_note="Idempotency verification",
        ),
    )

    # First fetch -> calls network
    art1 = acq_svc.fetch_source(source.id, commit=True)
    assert art1.extraction_status == QuestionAcquisitionExtractionStatus.COMPLETE
    assert fetch_calls == 1

    # Second fetch -> short circuits, does NOT call network
    art2 = acq_svc.fetch_source(source.id, commit=True)
    assert fetch_calls == 1
    assert art2.id == art1.id


# ==============================================================================
# SECTION 100: StreamIngestValidator Chunk Split & Boundary Tests
# ==============================================================================


def test_stream_ingest_validator_split_magic_header() -> None:
    """StreamIngestValidator must correctly accumulate %PDF- across small chunk boundaries."""
    # 1. Valid split chunks: b"%P" + b"DF-" + b"1.4\ncontent"
    val = StreamIngestValidator(max_bytes=1024)
    val.process_chunk(b"%P")
    val.process_chunk(b"DF-")
    val.process_chunk(b"1.4\nHello world")
    sha, total = val.finalize()
    assert total == 2 + 3 + 15
    assert len(sha) == 64

    # 2. Invalid split header: b"%P" + b"XX-" -> rejects immediately on chunk 2
    val_bad = StreamIngestValidator(max_bytes=1024)
    val_bad.process_chunk(b"%P")
    with pytest.raises(ApplicationError) as exc_bad:
        val_bad.process_chunk(b"XX-")
    assert exc_bad.value.code == "QUESTION_ACQUISITION_NOT_PDF"

    # 3. Empty stream -> rejects on finalize
    val_empty = StreamIngestValidator(max_bytes=1024)
    with pytest.raises(ApplicationError) as exc_empty:
        val_empty.finalize()
    assert exc_empty.value.code == "QUESTION_ACQUISITION_NOT_PDF"

    # 4. Truncated stream under 5 bytes -> rejects on finalize
    val_trunc = StreamIngestValidator(max_bytes=1024)
    val_trunc.process_chunk(b"%PD")
    with pytest.raises(ApplicationError) as exc_trunc:
        val_trunc.finalize()
    assert exc_trunc.value.code == "QUESTION_ACQUISITION_NOT_PDF"

    # 5. Oversized stream -> rejects on boundary
    val_large = StreamIngestValidator(max_bytes=10)
    val_large.process_chunk(b"%PDF-")
    with pytest.raises(ApplicationError) as exc_large:
        val_large.process_chunk(b"123456")  # 5 + 6 = 11 > 10
    assert exc_large.value.code == "QUESTION_ACQUISITION_FILE_TOO_LARGE"


# ==============================================================================
# SECTION 101: Transaction Boundaries & Concurrency Hardening Regression Tests
# ==============================================================================


def test_network_fetch_runs_without_active_db_transaction(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network fetch must execute when the SQLAlchemy session has no active transaction (session.in_transaction() is False)."""
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    valid_pdf = _build_test_pdf(["Session Invariant Test Exam"])
    network_called = False

    class AssertingFetcher(SafePdfFetcher):
        def fetch_pdf(self, start_url: str) -> FetchResult:
            nonlocal network_called
            network_called = True
            # CRITICAL ASSERTION: session must not be inside an active transaction during network call
            assert db_session.in_transaction() is False

            import tempfile, hashlib
            tf = tempfile.NamedTemporaryFile(prefix="test_tx_", suffix=".tmp", delete=False)
            tf.write(valid_pdf)
            tf.close()
            return FetchResult(
                temp_file_path=Path(tf.name),
                file_size_bytes=len(valid_pdf),
                sha256=hashlib.sha256(valid_pdf).hexdigest(),
                mime_type="application/pdf",
            )

    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    fetcher = AssertingFetcher(allowed_domains="trusted.edu.vn")
    acq_svc = QuestionAcquisitionService(db_session, fetcher=fetcher)

    source = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/no_tx_exam.pdf",
            provenance_note="Transaction boundary verification",
        ),
    )

    artifact = acq_svc.fetch_source(source.id, commit=True)
    assert network_called is True
    assert artifact.extraction_status == QuestionAcquisitionExtractionStatus.COMPLETE
    assert source.status == QuestionAcquisitionSourceStatus.FETCHED


def test_source_fetching_state_committed_before_network(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase A must commit source.status = FETCHING before network call starts, observable by independent session."""
    orig_getaddrinfo = socket.getaddrinfo

    def mock_getaddrinfo(host, port, *args, **kwargs):
        if host in {"localhost", "127.0.0.1"}:
            return orig_getaddrinfo(host, port, *args, **kwargs)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    valid_pdf = _build_test_pdf(["Phase A Observability Test Exam"])
    observed_status_in_second_session = None

    class ObservingFetcher(SafePdfFetcher):
        def fetch_pdf(self, start_url: str) -> FetchResult:
            nonlocal observed_status_in_second_session
            # Open an independent session sharing the test engine to observe committed DB state
            IndependentSession = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
            with IndependentSession() as other_session:
                other_source = other_session.get(QuestionAcquisitionSource, source.id)
                if other_source is not None:
                    observed_status_in_second_session = other_source.status

            import tempfile, hashlib
            tf = tempfile.NamedTemporaryFile(prefix="test_obs_", suffix=".tmp", delete=False)
            tf.write(valid_pdf)
            tf.close()
            return FetchResult(
                temp_file_path=Path(tf.name),
                file_size_bytes=len(valid_pdf),
                sha256=hashlib.sha256(valid_pdf).hexdigest(),
                mime_type="application/pdf",
            )

    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    fetcher = ObservingFetcher(allowed_domains="trusted.edu.vn")
    acq_svc = QuestionAcquisitionService(db_session, fetcher=fetcher)

    source = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/observable_exam.pdf",
            provenance_note="Phase A commit observability verification",
        ),
    )

    artifact = acq_svc.fetch_source(source.id, commit=True)
    assert observed_status_in_second_session == QuestionAcquisitionSourceStatus.FETCHING
    assert artifact.extraction_status == QuestionAcquisitionExtractionStatus.COMPLETE
    assert source.status == QuestionAcquisitionSourceStatus.FETCHED


def test_success_wins_over_late_failure(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When attempt A succeeds and links a usable artifact, a late failure in attempt B must not overwrite FETCHED with FAILED."""
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    valid_pdf = _build_test_pdf(["Attempt A Success PDF"])

    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    source = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/race_race.pdf",
            provenance_note="Race test provenance",
        ),
    )

    # Simulate Attempt B enters Phase A (FETCHING)
    _, prepared_b = acq_svc._prepare_source_fetch(source.id)
    assert prepared_b is not None
    assert source.status == QuestionAcquisitionSourceStatus.FETCHING

    # Now Attempt A executes and completes successfully
    import tempfile, hashlib
    with tempfile.NamedTemporaryFile(prefix="acq_a_", suffix=".tmp", delete=False) as tf:
        tf.write(valid_pdf)
        temp_a_path = Path(tf.name)

    try:
        art_a = acq_svc._finalize_fetch_success(
            prepared=prepared_b,
            fetch_result=FetchResult(
                temp_file_path=temp_a_path,
                file_size_bytes=len(valid_pdf),
                sha256=hashlib.sha256(valid_pdf).hexdigest(),
                mime_type="application/pdf",
            ),
            commit=True,
        )
        assert art_a.extraction_status == QuestionAcquisitionExtractionStatus.COMPLETE
        assert source.status == QuestionAcquisitionSourceStatus.FETCHED

        # Now Attempt B fails its network call and runs Phase C failure finalization
        acq_svc._finalize_fetch_failure(
            prepared_b.source_id,
            failure_code="QUESTION_ACQUISITION_FETCH_FAILED",
            failure_detail="Connection reset by peer on attempt B",
            commit=True,
        )

        # CRITICAL ASSERTION: source must still be FETCHED, not FAILED!
        db_session.expire_all()
        reloaded = db_session.get(QuestionAcquisitionSource, source.id)
        assert reloaded is not None
        assert reloaded.status == QuestionAcquisitionSourceStatus.FETCHED
        assert reloaded.failure_code is None
        assert reloaded.failure_detail is None

        # Request status remains READY_FOR_REVIEW
        reloaded_req = acq_svc.get_request(acq_req.id)
        assert reloaded_req is not None
        assert reloaded_req.status == QuestionAcquisitionRequestStatus.READY_FOR_REVIEW
    finally:
        temp_a_path.unlink(missing_ok=True)


def test_block_during_fetch(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When an admin blocks a source while network fetch is in flight, the downloaded artifact is linked for audit but source remains BLOCKED and request is not promoted."""
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    valid_pdf = _build_test_pdf(["Blocked Content In Flight"])

    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    source = acq_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/takedown.pdf",
            provenance_note="Takedown test provenance",
        ),
    )

    # 1. Prepare fetch (Phase A -> FETCHING)
    _, prepared = acq_svc._prepare_source_fetch(source.id)
    assert prepared is not None
    assert source.status == QuestionAcquisitionSourceStatus.FETCHING

    # 2. While network is in flight, Admin blocks the source
    blocked_source = acq_svc.block_source(
        source.id, reason="Copyright claim received mid-download", commit=True
    )
    assert blocked_source.status == QuestionAcquisitionSourceStatus.BLOCKED
    assert blocked_source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED

    # 3. Network fetch completes and finalizes success
    import tempfile, hashlib
    with tempfile.NamedTemporaryFile(prefix="acq_block_", suffix=".tmp", delete=False) as tf:
        tf.write(valid_pdf)
        temp_path = Path(tf.name)

    try:
        artifact = acq_svc._finalize_fetch_success(
            prepared=prepared,
            fetch_result=FetchResult(
                temp_file_path=temp_path,
                file_size_bytes=len(valid_pdf),
                sha256=hashlib.sha256(valid_pdf).hexdigest(),
                mime_type="application/pdf",
            ),
            commit=True,
        )
        assert artifact is not None

        # CRITICAL ASSERTIONS:
        # - Source remains BLOCKED (NOT resurrected to FETCHED!)
        reloaded_source = db_session.get(QuestionAcquisitionSource, source.id)
        assert reloaded_source is not None
        assert reloaded_source.status == QuestionAcquisitionSourceStatus.BLOCKED
        assert reloaded_source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED

        # - Artifact and link are retained for audit trail
        links = db_session.scalars(
            select(QuestionAcquisitionSourceArtifact).where(
                QuestionAcquisitionSourceArtifact.source_id == source.id
            )
        ).all()
        assert len(links) == 1
        assert links[0].artifact_id == artifact.id

        # - Request must NOT become READY_FOR_REVIEW from this blocked source
        reloaded_req = acq_svc.get_request(acq_req.id)
        assert reloaded_req is not None
        assert reloaded_req.status == QuestionAcquisitionRequestStatus.AWAITING_SOURCE
    finally:
        temp_path.unlink(missing_ok=True)


def test_transport_exception_mapping_coverage() -> None:
    """map_httpcore_transport_exceptions must cleanly map all public httpcore transport errors to httpx equivalents."""
    from app.question_acquisition.fetcher import map_httpcore_transport_exceptions

    exception_cases = [
        (httpcore.ConnectTimeout("conn timeout"), httpx.ConnectTimeout),
        (httpcore.ReadTimeout("read timeout"), httpx.ReadTimeout),
        (httpcore.WriteTimeout("write timeout"), httpx.WriteTimeout),
        (httpcore.PoolTimeout("pool timeout"), httpx.PoolTimeout),
        (httpcore.ConnectError("conn error"), httpx.ConnectError),
        (httpcore.ReadError("read error"), httpx.ReadError),
        (httpcore.WriteError("write error"), httpx.WriteError),
        (httpcore.ProxyError("proxy error"), httpx.ProxyError),
        (httpcore.UnsupportedProtocol("unsupported"), httpx.UnsupportedProtocol),
        (httpcore.LocalProtocolError("local proto"), httpx.ProtocolError),
        (httpcore.RemoteProtocolError("remote proto"), httpx.ProtocolError),
        (httpcore.ProtocolError("proto error"), httpx.ProtocolError),
        (httpcore.NetworkError("network error"), httpx.NetworkError),
    ]

    for hc_exc, expected_hx_type in exception_cases:
        with pytest.raises(expected_hx_type) as exc_info:
            with map_httpcore_transport_exceptions():
                raise hc_exc
        assert isinstance(exc_info.value, httpx.RequestError)


def test_pinned_transport_and_stream_timeout_mapping() -> None:
    """PinnedTransport and PinnedResponseStream must raise httpx timeout subtypes when pool or stream times out."""
    class TimeoutPool:
        def handle_request(self, req: httpcore.Request) -> httpcore.Response:
            raise httpcore.ConnectTimeout("Connection timed out")

        def close(self) -> None:
            pass

    transport = PinnedTransport({"timeout.edu.vn": "93.184.216.34"}, pool=TimeoutPool())
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ConnectTimeout):
            client.get("https://timeout.edu.vn/doc.pdf")

    class TimeoutStream:
        def __iter__(self):
            yield b"%PDF-1.4"
            raise httpcore.ReadTimeout("Stream read timed out")

    class TimeoutStreamPool:
        def handle_request(self, req: httpcore.Request) -> httpcore.Response:
            return httpcore.Response(200, content=TimeoutStream())

        def close(self) -> None:
            pass

    stream_transport = PinnedTransport({"stream.edu.vn": "93.184.216.34"}, pool=TimeoutStreamPool())
    with httpx.Client(transport=stream_transport) as client:
        with client.stream("GET", "https://stream.edu.vn/doc.pdf") as resp:
            with pytest.raises(httpx.ReadTimeout):
                list(resp.iter_bytes())


# ==============================================================================
# SECTION 102: Cross-Session Concurrency & Identity-Map Refresh Regression Tests
# ==============================================================================


def test_cross_session_block_wins_over_fetch_success(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session A prepares fetch. Session B blocks source mid-download and commits. Session A finalizes success.

    Session A's stale identity map must be refreshed via populate_existing=True:
    source must remain BLOCKED, manual block failure fields must not be overwritten,
    artifact is linked for audit, and request must not transition to READY_FOR_REVIEW.
    """
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    valid_pdf = _build_test_pdf(["Cross Session Block Success Content"])

    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    seed_svc = QuestionAcquisitionService(db_session)
    source = seed_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/cs_block_success.pdf",
            provenance_note="Cross session block test",
        ),
    )
    db_session.commit()

    SessionFactory = sessionmaker(
        bind=db_session.get_bind(), autoflush=False, expire_on_commit=False
    )
    session_a = SessionFactory()
    session_b = SessionFactory()

    try:
        svc_a = QuestionAcquisitionService(session_a)
        # Phase A in Session A -> source.status = FETCHING committed
        _, prepared = svc_a._prepare_source_fetch(source.id)
        assert prepared is not None
        source_in_a = session_a.get(QuestionAcquisitionSource, source.id)
        assert source_in_a is not None
        assert source_in_a.status == QuestionAcquisitionSourceStatus.FETCHING

        # Session B loads the source and blocks it while Session A is in network
        svc_b = QuestionAcquisitionService(session_b)
        blocked_source = svc_b.block_source(
            source.id, reason="Copyright claim received mid-download", commit=True
        )
        assert blocked_source.status == QuestionAcquisitionSourceStatus.BLOCKED
        assert blocked_source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED
        assert blocked_source.failure_code == "MANUALLY_BLOCKED"
        assert blocked_source.failure_detail == "Copyright claim received mid-download"
        session_b.close()

        # Session A completes network download and finalizes success in Phase C
        import tempfile, hashlib
        with tempfile.NamedTemporaryFile(prefix="cs_blk_succ_", suffix=".tmp", delete=False) as tf:
            tf.write(valid_pdf)
            temp_path = Path(tf.name)

        try:
            artifact = svc_a._finalize_fetch_success(
                prepared=prepared,
                fetch_result=FetchResult(
                    temp_file_path=temp_path,
                    file_size_bytes=len(valid_pdf),
                    sha256=hashlib.sha256(valid_pdf).hexdigest(),
                    mime_type="application/pdf",
                ),
                commit=True,
            )
            assert artifact is not None

            # Assertions in Session A:
            # - source identity map was refreshed via populate_existing=True and remains BLOCKED
            reloaded_a = session_a.get(QuestionAcquisitionSource, source.id)
            assert reloaded_a is not None
            assert reloaded_a.status == QuestionAcquisitionSourceStatus.BLOCKED
            assert reloaded_a.rights_status == QuestionAcquisitionRightsStatus.BLOCKED
            assert reloaded_a.failure_code == "MANUALLY_BLOCKED"
            assert reloaded_a.failure_detail == "Copyright claim received mid-download"

            # Assertions in fresh independent verification session:
            with SessionFactory() as session_verify:
                v_source = session_verify.get(QuestionAcquisitionSource, source.id)
                assert v_source is not None
                assert v_source.status == QuestionAcquisitionSourceStatus.BLOCKED
                assert v_source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED
                assert v_source.failure_code == "MANUALLY_BLOCKED"
                assert v_source.failure_detail == "Copyright claim received mid-download"

                # Artifact and link retained for audit
                v_links = session_verify.scalars(
                    select(QuestionAcquisitionSourceArtifact).where(
                        QuestionAcquisitionSourceArtifact.source_id == source.id
                    )
                ).all()
                assert len(v_links) == 1
                assert v_links[0].artifact_id == artifact.id

                # Request must NOT be READY_FOR_REVIEW
                v_req = session_verify.get(QuestionAcquisitionRequest, acq_req.id)
                assert v_req is not None
                assert v_req.status != QuestionAcquisitionRequestStatus.READY_FOR_REVIEW
                assert v_req.status == QuestionAcquisitionRequestStatus.AWAITING_SOURCE
        finally:
            temp_path.unlink(missing_ok=True)
    finally:
        session_a.close()


def test_cross_session_block_wins_over_fetch_failure(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session A prepares fetch. Session B blocks source mid-download and commits. Session A fails network.

    Session A failure finalizer must reload fresh DB state:
    source must remain BLOCKED (NOT FAILED), and manual block reason must not be overwritten.
    """
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    seed_svc = QuestionAcquisitionService(db_session)
    source = seed_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/cs_block_fail.pdf",
            provenance_note="Cross session block failure test",
        ),
    )
    db_session.commit()

    SessionFactory = sessionmaker(
        bind=db_session.get_bind(), autoflush=False, expire_on_commit=False
    )
    session_a = SessionFactory()
    session_b = SessionFactory()

    try:
        svc_a = QuestionAcquisitionService(session_a)
        _, prepared = svc_a._prepare_source_fetch(source.id)
        assert prepared is not None

        # Session B blocks the source while Session A is in flight
        svc_b = QuestionAcquisitionService(session_b)
        svc_b.block_source(
            source.id, reason="Takedown notice received while downloading", commit=True
        )
        session_b.close()

        # Session A network call fails and runs Phase C failure finalization
        svc_a._finalize_fetch_failure(
            prepared.source_id,
            failure_code="QUESTION_ACQUISITION_FETCH_FAILED",
            failure_detail="Connection timeout on attempt A",
            commit=True,
        )

        # Assertions:
        source_in_a = session_a.get(QuestionAcquisitionSource, source.id)
        assert source_in_a is not None
        assert source_in_a.status == QuestionAcquisitionSourceStatus.BLOCKED
        assert source_in_a.rights_status == QuestionAcquisitionRightsStatus.BLOCKED
        assert source_in_a.failure_code == "MANUALLY_BLOCKED"
        assert source_in_a.failure_detail == "Takedown notice received while downloading"

        with SessionFactory() as session_verify:
            v_source = session_verify.get(QuestionAcquisitionSource, source.id)
            assert v_source is not None
            assert v_source.status == QuestionAcquisitionSourceStatus.BLOCKED
            assert v_source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED
            assert v_source.failure_code == "MANUALLY_BLOCKED"
            assert v_source.failure_detail == "Takedown notice received while downloading"

            v_req = session_verify.get(QuestionAcquisitionRequest, acq_req.id)
            assert v_req is not None
            assert v_req.status == QuestionAcquisitionRequestStatus.AWAITING_SOURCE
    finally:
        session_a.close()


def test_cross_session_late_failure_after_other_success(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session A prepares fetch. Session B fetches and finalizes usable artifact. Session A fails network late.

    Session A failure finalizer must observe Session B's usable artifact:
    source remains FETCHED (NOT overwritten with FAILED), failure fields stay null.
    """
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    valid_pdf = _build_test_pdf(["Cross Session Late Failure Contest Exam"])

    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    seed_svc = QuestionAcquisitionService(db_session)
    source = seed_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/cs_late_fail.pdf",
            provenance_note="Cross session late failure test",
        ),
    )
    db_session.commit()

    SessionFactory = sessionmaker(
        bind=db_session.get_bind(), autoflush=False, expire_on_commit=False
    )
    session_a = SessionFactory()
    session_b = SessionFactory()

    try:
        svc_a = QuestionAcquisitionService(session_a)
        _, prepared_a = svc_a._prepare_source_fetch(source.id)
        assert prepared_a is not None

        # Session B prepares and finalizes success with a usable artifact
        svc_b = QuestionAcquisitionService(session_b)
        _, prepared_b = svc_b._prepare_source_fetch(source.id)
        assert prepared_b is not None

        import tempfile, hashlib
        with tempfile.NamedTemporaryFile(prefix="cs_b_succ_", suffix=".tmp", delete=False) as tf:
            tf.write(valid_pdf)
            temp_path = Path(tf.name)

        try:
            art_b = svc_b._finalize_fetch_success(
                prepared=prepared_b,
                fetch_result=FetchResult(
                    temp_file_path=temp_path,
                    file_size_bytes=len(valid_pdf),
                    sha256=hashlib.sha256(valid_pdf).hexdigest(),
                    mime_type="application/pdf",
                ),
                commit=True,
            )
            assert art_b.extraction_status == QuestionAcquisitionExtractionStatus.COMPLETE
            session_b.close()

            # Session A network call times out late and runs Phase C failure finalization
            svc_a._finalize_fetch_failure(
                prepared_a.source_id,
                failure_code="QUESTION_ACQUISITION_FETCH_FAILED",
                failure_detail="Late network timeout on Session A",
                commit=True,
            )

            # Assertions: Session A reloads fresh row and sees usable artifact -> FETCHED!
            source_in_a = session_a.get(QuestionAcquisitionSource, source.id)
            assert source_in_a is not None
            assert source_in_a.status == QuestionAcquisitionSourceStatus.FETCHED
            assert source_in_a.failure_code is None
            assert source_in_a.failure_detail is None

            with SessionFactory() as session_verify:
                v_source = session_verify.get(QuestionAcquisitionSource, source.id)
                assert v_source is not None
                assert v_source.status == QuestionAcquisitionSourceStatus.FETCHED
                assert v_source.failure_code is None
                assert v_source.failure_detail is None

                v_req = session_verify.get(QuestionAcquisitionRequest, acq_req.id)
                assert v_req is not None
                assert v_req.status == QuestionAcquisitionRequestStatus.READY_FOR_REVIEW
        finally:
            temp_path.unlink(missing_ok=True)
    finally:
        session_a.close()


def test_load_source_for_finalization_refreshes_stale_identity_map(
    db_session: Session,
    practice_content: PracticeContent,
) -> None:
    """Directly verifies that _load_source_for_finalization with populate_existing=True refreshes stale identity-map instances."""
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    seed_svc = QuestionAcquisitionService(db_session)
    source = seed_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/direct_refresh.pdf",
            provenance_note="Identity map refresh verification",
        ),
    )
    db_session.commit()

    SessionFactory = sessionmaker(
        bind=db_session.get_bind(), autoflush=False, expire_on_commit=False
    )
    session_a = SessionFactory()
    session_b = SessionFactory()

    try:
        # Session A loads source into identity map (status == REGISTERED)
        source_in_a = session_a.get(QuestionAcquisitionSource, source.id)
        assert source_in_a is not None
        assert source_in_a.status == QuestionAcquisitionSourceStatus.REGISTERED

        # Session B updates and commits the row to BLOCKED
        source_in_b = session_b.get(QuestionAcquisitionSource, source.id)
        assert source_in_b is not None
        source_in_b.status = QuestionAcquisitionSourceStatus.BLOCKED
        source_in_b.rights_status = QuestionAcquisitionRightsStatus.BLOCKED
        source_in_b.failure_code = "MANUALLY_BLOCKED"
        source_in_b.failure_detail = "Proof of populate_existing"
        session_b.commit()
        session_b.close()

        # Regular session_a.get() without populate_existing returns cached stale state from identity map
        cached_source = session_a.get(QuestionAcquisitionSource, source.id)
        assert cached_source is not None
        assert cached_source.status == QuestionAcquisitionSourceStatus.REGISTERED

        # _load_source_for_finalization MUST refresh the in-memory instance via populate_existing=True
        svc_a = QuestionAcquisitionService(session_a)
        fresh_source = svc_a._load_source_for_finalization(source.id)
        assert fresh_source is not None
        assert fresh_source.status == QuestionAcquisitionSourceStatus.BLOCKED
        assert fresh_source.rights_status == QuestionAcquisitionRightsStatus.BLOCKED
        assert fresh_source.failure_code == "MANUALLY_BLOCKED"
        assert fresh_source.failure_detail == "Proof of populate_existing"

        # Even regular get now reflects refreshed state on the same python instance
        cached_after = session_a.get(QuestionAcquisitionSource, source.id)
        assert cached_after is not None
        assert cached_after.status == QuestionAcquisitionSourceStatus.BLOCKED
    finally:
        session_a.close()


def test_late_failed_artifact_does_not_downgrade_usable_source(
    db_session: Session,
    practice_content: PracticeContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a source already has a usable (COMPLETE/PARTIAL) artifact, a concurrent fetch finalizing a FAILED artifact later must not downgrade the source from FETCHED to FAILED or demote request."""
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    # Invariant: zero Question side effects
    q_count_before = db_session.scalar(select(func.count(Question.id)))

    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    seed_svc = QuestionAcquisitionService(db_session)
    source = seed_svc.register_source(
        acq_req.id,
        RegisterSourceRequest(
            source_kind=QuestionAcquisitionSourceKind.PDF_URL,
            url="https://trusted.edu.vn/late_fail_race.pdf",
            provenance_note="Late failed artifact race test",
        ),
    )
    db_session.commit()

    SessionFactory = sessionmaker(
        bind=db_session.get_bind(), autoflush=False, expire_on_commit=False
    )
    session_a = SessionFactory()
    session_b = SessionFactory()

    try:
        svc_a = QuestionAcquisitionService(session_a)
        _, prepared_a = svc_a._prepare_source_fetch(source.id)
        assert prepared_a is not None

        # Session B prepares and finalizes valid artifact -> COMPLETE -> source FETCHED
        svc_b = QuestionAcquisitionService(session_b)
        _, prepared_b = svc_b._prepare_source_fetch(source.id)
        assert prepared_b is not None

        valid_pdf = _build_test_pdf(["Attempt B Valid Content"])
        import tempfile, hashlib
        with tempfile.NamedTemporaryFile(prefix="cs_b_valid_", suffix=".tmp", delete=False) as tf:
            tf.write(valid_pdf)
            temp_b_path = Path(tf.name)

        try:
            art_b = svc_b._finalize_fetch_success(
                prepared=prepared_b,
                fetch_result=FetchResult(
                    temp_file_path=temp_b_path,
                    file_size_bytes=len(valid_pdf),
                    sha256=hashlib.sha256(valid_pdf).hexdigest(),
                    mime_type="application/pdf",
                ),
                commit=True,
            )
            assert art_b.extraction_status == QuestionAcquisitionExtractionStatus.COMPLETE
            session_b.close()

            # Session A finalizes later with a zero-text PDF -> extraction FAILED
            zero_text_pdf = _build_test_pdf(["", ""])
            with tempfile.NamedTemporaryFile(prefix="cs_a_zero_", suffix=".tmp", delete=False) as tf:
                tf.write(zero_text_pdf)
                temp_a_path = Path(tf.name)

            try:
                art_a = svc_a._finalize_fetch_success(
                    prepared=prepared_a,
                    fetch_result=FetchResult(
                        temp_file_path=temp_a_path,
                        file_size_bytes=len(zero_text_pdf),
                        sha256=hashlib.sha256(zero_text_pdf).hexdigest(),
                        mime_type="application/pdf",
                    ),
                    commit=True,
                )
                assert art_a.extraction_status == QuestionAcquisitionExtractionStatus.FAILED
                session_a.close()

                # Fresh verification session
                with SessionFactory() as session_verify:
                    v_source = session_verify.get(QuestionAcquisitionSource, source.id)
                    assert v_source is not None
                    # Source remains FETCHED (NOT downgraded to FAILED!)
                    assert v_source.status == QuestionAcquisitionSourceStatus.FETCHED
                    # Failure fields are cleared because aggregate state is usable
                    assert v_source.failure_code is None
                    assert v_source.failure_detail is None

                    # Exactly 2 artifact links exist for audit history (one COMPLETE, one FAILED)
                    links = session_verify.scalars(
                        select(QuestionAcquisitionSourceArtifact).where(
                            QuestionAcquisitionSourceArtifact.source_id == source.id
                        )
                    ).all()
                    assert len(links) == 2
                    statuses = {link.artifact.extraction_status for link in links}
                    assert statuses == {
                        QuestionAcquisitionExtractionStatus.COMPLETE,
                        QuestionAcquisitionExtractionStatus.FAILED,
                    }

                    # Request must remain READY_FOR_REVIEW
                    v_req = session_verify.get(QuestionAcquisitionRequest, acq_req.id)
                    assert v_req is not None
                    assert v_req.status == QuestionAcquisitionRequestStatus.READY_FOR_REVIEW

                    # Invariant: zero Question side effects
                    q_count_after = session_verify.scalar(select(func.count(Question.id)))
                    assert q_count_after == q_count_before
            finally:
                temp_a_path.unlink(missing_ok=True)
        finally:
            temp_b_path.unlink(missing_ok=True)
    finally:
        session_a.close()


def test_source_state_uses_all_linked_artifacts_not_current_artifact_only(
    db_session: Session,
    practice_content: PracticeContent,
) -> None:
    """_ingest_artifact_file resolves aggregate source status over all linked artifacts, not just the latest one."""
    _, acq_req = _create_test_gap_and_request(db_session, practice_content)
    acq_svc = QuestionAcquisitionService(db_session)

    # 1. Ingest usable artifact first
    valid_pdf = _build_test_pdf(["Usable Base Question"])
    source, art1 = acq_svc.upload_artifact(
        acq_req.id,
        file_bytes=valid_pdf,
        provenance_note="Usable base artifact",
    )
    assert source.status == QuestionAcquisitionSourceStatus.FETCHED
    assert art1.extraction_status == QuestionAcquisitionExtractionStatus.COMPLETE

    # 2. Ingest failed artifact into the same source
    zero_text_pdf = _build_test_pdf(["", ""])
    import tempfile, hashlib
    with tempfile.NamedTemporaryFile(prefix="fail_ingest_", suffix=".tmp", delete=False) as tf:
        tf.write(zero_text_pdf)
        temp_path = Path(tf.name)

    try:
        art2 = acq_svc._ingest_artifact_file(
            source=source,
            file_path=temp_path,
            sha256=hashlib.sha256(zero_text_pdf).hexdigest(),
            file_size_bytes=len(zero_text_pdf),
            mime_type="application/pdf",
        )
        assert art2.extraction_status == QuestionAcquisitionExtractionStatus.FAILED

        # Source remains FETCHED because art1 is usable
        assert source.status == QuestionAcquisitionSourceStatus.FETCHED
        assert source.failure_code is None
        assert source.failure_detail is None

        # Both artifacts remain linked for audit trail
        links = db_session.scalars(
            select(QuestionAcquisitionSourceArtifact).where(
                QuestionAcquisitionSourceArtifact.source_id == source.id
            )
        ).all()
        assert len(links) == 2
    finally:
        temp_path.unlink(missing_ok=True)




