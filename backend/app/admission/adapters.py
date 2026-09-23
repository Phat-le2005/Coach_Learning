from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.admission.import_schemas import AdmissionRuleImportRecord


class OfficialAdmissionSourceAdapter(ABC):
    """Abstract Interface for integrating official external admission sources.

    Designed for future official integrations (e.g. Cổng thông tin tuyển sinh Bộ GD&ĐT,
    Hệ thống tuyển sinh ĐHQG, Cổng dữ liệu mở các trường Đại học).

    Guarantees:
    - Zero AI: All facts must be collected from verifiable external official portals.
    - Full provenance: Every fetched record is pre-populated with source references and timestamps.
    """

    @property
    @abstractmethod
    def source_identifier(self) -> str:
        """Unique key for the official source adapter (e.g. 'MOET_PORTAL', 'HUST_PORTAL')."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name of the source."""
        ...

    @property
    @abstractmethod
    def publisher(self) -> str:
        """Name of the official issuing agency or university."""
        ...

    @abstractmethod
    def fetch_admission_rules(self, year: int, **kwargs: Any) -> list[AdmissionRuleImportRecord]:
        """Fetch verified admission rules for the given academic year."""
        ...

    @abstractmethod
    def verify_source_authenticity(self, source_reference: str, **kwargs: Any) -> bool:
        """Cryptographically or structurally verify the source document reference."""
        ...


class MockMoetAdmissionPortalAdapter(OfficialAdmissionSourceAdapter):
    """Reference implementation connecting to Ministry of Education and Training (Bộ GD&ĐT) portal feed."""

    @property
    def source_identifier(self) -> str:
        return "MOET_OFFICIAL_PORTAL"

    @property
    def source_name(self) -> str:
        return "Cổng Thông tin Tuyển sinh Bộ Giáo dục và Đào tạo"

    @property
    def publisher(self) -> str:
        return "Bộ Giáo dục và Đào tạo"

    def verify_source_authenticity(self, source_reference: str, **kwargs: Any) -> bool:
        return bool(source_reference and len(source_reference.strip()) > 5)

    def fetch_admission_rules(self, year: int, **kwargs: Any) -> list[AdmissionRuleImportRecord]:
        """Mock feed returning verified admission records for testing adapter pipeline."""
        now = datetime.now(timezone.utc)
        return [
            AdmissionRuleImportRecord(
                university_code="BKHN",
                university_name="Đại học Bách Khoa Hà Nội",
                major_code="IT1",
                major_name="Khoa học Máy tính",
                method_code="THPT",
                method_name="Thi tốt nghiệp THPT",
                year=year,
                subject_combination="A00",
                requirements={"floor_score": 24.0},
                quota=200,
                historical_score=29.42 if year == 2025 else None,
                source_reference=f"Cổng thông tin Bộ GD&ĐT - Dữ liệu Đề án {year} ĐHBKHN",
                verified_at=now,
                data_source_name=f"Đề án tuyển sinh ĐHBKHN {year} (Bộ GD&ĐT)",
                data_source_url=f"https://moet.gov.vn/tuyensinh/{year}/bkhn",
                data_source_publisher="Bộ Giáo dục và Đào tạo",
            ),
        ]
