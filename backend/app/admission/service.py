from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

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
    AdmissionRuleRead,
    AdmissionRuleUpdate,
    AdmissionTargetCreate,
    AdmissionTargetRead,
    AdmissionTargetUpdate,
    MajorCreate,
    MajorRead,
    UniversityCreate,
    UniversityRead,
)
from app.core.exceptions import ApplicationError

logger = logging.getLogger(__name__)


class AdmissionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --------------------------------------------------------------------------
    # Universities
    # --------------------------------------------------------------------------

    def list_universities(
        self,
        search: str | None = None,
        region: str | None = None,
        is_active: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> list[UniversityRead]:
        stmt = (
            select(
                University,
                func.count(Major.id).label("majors_count"),
            )
            .outerjoin(Major, (Major.university_id == University.id) & (Major.is_active.is_(True)))
            .where(University.is_active == is_active)
            .group_by(University.id)
            .order_by(University.code.asc())
        )

        if region:
            stmt = stmt.where(University.region == region)

        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    University.name.ilike(pattern),
                    University.code.ilike(pattern),
                    University.short_name.ilike(pattern),
                )
            )

        stmt = stmt.offset(offset).limit(limit)
        results = self.session.execute(stmt).all()

        return [
            UniversityRead(
                id=u.id,
                code=u.code,
                name=u.name,
                short_name=u.short_name,
                description=u.description,
                website=u.website,
                region=u.region,
                is_active=u.is_active,
                majors_count=majors_count,
                created_at=u.created_at,
                updated_at=u.updated_at,
            )
            for u, majors_count in results
        ]

    def get_university(self, university_id: UUID) -> University:
        university = self.session.get(University, university_id)
        if not university:
            raise ApplicationError(404, "UNIVERSITY_NOT_FOUND", "University was not found.")
        return university

    def create_university(self, data: UniversityCreate) -> University:
        existing = self.session.scalar(
            select(University).where(University.code == data.code)
        )
        if existing:
            raise ApplicationError(
                409, "UNIVERSITY_CODE_EXISTS", f"University code '{data.code}' already exists."
            )

        university = University(
            code=data.code,
            name=data.name,
            short_name=data.short_name,
            description=data.description,
            website=data.website,
            region=data.region,
            is_active=data.is_active,
        )
        self.session.add(university)
        self.session.commit()
        self.session.refresh(university)
        return university

    # --------------------------------------------------------------------------
    # Majors
    # --------------------------------------------------------------------------

    def list_majors_by_university(
        self,
        university_id: UUID,
        search: str | None = None,
        is_active: bool = True,
    ) -> list[MajorRead]:
        self.get_university(university_id)

        stmt = (
            select(Major)
            .where(Major.university_id == university_id)
            .where(Major.is_active == is_active)
            .order_by(Major.code.asc())
        )

        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Major.name.ilike(pattern),
                    Major.code.ilike(pattern),
                )
            )

        majors = self.session.scalars(stmt).all()
        return [MajorRead.model_validate(m) for m in majors]

    def get_major(self, major_id: UUID) -> Major:
        major = self.session.get(Major, major_id)
        if not major:
            raise ApplicationError(404, "MAJOR_NOT_FOUND", "Major was not found.")
        return major

    def create_major(self, data: MajorCreate) -> Major:
        self.get_university(data.university_id)

        existing = self.session.scalar(
            select(Major).where(
                Major.university_id == data.university_id,
                Major.code == data.code,
            )
        )
        if existing:
            raise ApplicationError(
                409,
                "MAJOR_CODE_EXISTS",
                f"Major code '{data.code}' already exists for this university.",
            )

        major = Major(
            university_id=data.university_id,
            code=data.code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
        )
        self.session.add(major)
        self.session.commit()
        self.session.refresh(major)
        return major

    # --------------------------------------------------------------------------
    # Admission Methods & Data Sources
    # --------------------------------------------------------------------------

    def create_method(self, data: AdmissionMethodCreate) -> AdmissionMethod:
        existing = self.session.scalar(
            select(AdmissionMethod).where(AdmissionMethod.code == data.code)
        )
        if existing:
            raise ApplicationError(
                409,
                "ADMISSION_METHOD_CODE_EXISTS",
                f"Admission method code '{data.code}' already exists.",
            )

        method = AdmissionMethod(
            code=data.code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
        )
        self.session.add(method)
        self.session.commit()
        self.session.refresh(method)
        return method

    def create_data_source(self, data: AdmissionDataSourceCreate) -> AdmissionDataSource:
        ds = AdmissionDataSource(
            name=data.name,
            source_type=data.source_type,
            source_url=data.source_url,
            publisher=data.publisher,
            published_year=data.published_year,
            verified_at=data.verified_at,
            verified_by=data.verified_by,
        )
        self.session.add(ds)
        self.session.commit()
        self.session.refresh(ds)
        return ds

    # --------------------------------------------------------------------------
    # Admission Rules (Versioned by Year)
    # --------------------------------------------------------------------------

    def list_rules_by_major(
        self,
        major_id: UUID,
        year: int | None = None,
        method_id: UUID | None = None,
    ) -> list[AdmissionRuleRead]:
        self.get_major(major_id)

        stmt = (
            select(AdmissionRule)
            .options(
                joinedload(AdmissionRule.university),
                joinedload(AdmissionRule.major),
                joinedload(AdmissionRule.method),
                joinedload(AdmissionRule.data_source),
            )
            .where(AdmissionRule.major_id == major_id)
            .where(AdmissionRule.is_active.is_(True))
            .order_by(AdmissionRule.year.desc(), AdmissionRule.subject_combination.asc())
        )

        if year is not None:
            stmt = stmt.where(AdmissionRule.year == year)

        if method_id is not None:
            stmt = stmt.where(AdmissionRule.method_id == method_id)

        rules = self.session.scalars(stmt).unique().all()

        return [
            AdmissionRuleRead(
                id=r.id,
                university_id=r.university_id,
                university_name=r.university.name if r.university else "",
                major_id=r.major_id,
                major_name=r.major.name if r.major else "",
                year=r.year,
                method_id=r.method_id,
                method_code=r.method.code if r.method else "",
                method_name=r.method.name if r.method else "",
                subject_combination=r.subject_combination,
                requirements=r.requirements or {},
                quota=r.quota,
                historical_score=r.historical_score,
                source_reference=r.source_reference,
                data_source_id=r.data_source_id,
                verified_at=r.verified_at,
                is_active=r.is_active,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rules
        ]

    def create_rule(self, data: AdmissionRuleCreate) -> AdmissionRule:
        self.get_university(data.university_id)
        major = self.get_major(data.major_id)
        if major.university_id != data.university_id:
            raise ApplicationError(
                400,
                "MAJOR_UNIVERSITY_MISMATCH",
                "Specified major does not belong to the given university.",
            )

        method = self.session.get(AdmissionMethod, data.method_id)
        if not method:
            raise ApplicationError(404, "METHOD_NOT_FOUND", "Admission method was not found.")

        existing = self.session.scalar(
            select(AdmissionRule).where(
                AdmissionRule.major_id == data.major_id,
                AdmissionRule.year == data.year,
                AdmissionRule.method_id == data.method_id,
                AdmissionRule.subject_combination == data.subject_combination,
            )
        )
        if existing:
            raise ApplicationError(
                409,
                "RULE_ALREADY_EXISTS",
                f"Rule for major '{major.code}' year {data.year} with combination '{data.subject_combination}' already exists.",
            )

        rule = AdmissionRule(
            university_id=data.university_id,
            major_id=data.major_id,
            year=data.year,
            method_id=data.method_id,
            subject_combination=data.subject_combination,
            requirements=data.requirements,
            quota=data.quota,
            historical_score=data.historical_score,
            source_reference=data.source_reference,
            data_source_id=data.data_source_id,
            verified_at=data.verified_at,
            verified_by=data.verified_by,
            is_active=data.is_active,
        )
        self.session.add(rule)
        self.session.commit()
        self.session.refresh(rule)
        return rule

    # --------------------------------------------------------------------------
    # Student Admission Targets
    # --------------------------------------------------------------------------

    def list_student_targets(
        self,
        student_profile_id: UUID,
        target_year: int | None = None,
    ) -> list[AdmissionTargetRead]:
        stmt = (
            select(AdmissionTarget)
            .options(
                joinedload(AdmissionTarget.university),
                joinedload(AdmissionTarget.major),
            )
            .where(AdmissionTarget.student_id == student_profile_id)
            .order_by(AdmissionTarget.priority_order.asc(), AdmissionTarget.created_at.asc())
        )

        if target_year is not None:
            stmt = stmt.where(AdmissionTarget.target_year == target_year)

        targets = self.session.scalars(stmt).unique().all()

        return [
            AdmissionTargetRead(
                id=t.id,
                student_id=t.student_id,
                university_id=t.university_id,
                university_code=t.university.code if t.university else "",
                university_name=t.university.name if t.university else "",
                major_id=t.major_id,
                major_code=t.major.code if t.major else "",
                major_name=t.major.name if t.major else "",
                target_type=t.target_type,
                target_year=t.target_year,
                priority_order=t.priority_order,
                notes=t.notes,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in targets
        ]

    def create_student_target(
        self,
        student_profile_id: UUID,
        data: AdmissionTargetCreate,
    ) -> AdmissionTargetRead:
        university = self.get_university(data.university_id)
        major = self.get_major(data.major_id)

        if major.university_id != university.id:
            raise ApplicationError(
                400,
                "MAJOR_UNIVERSITY_MISMATCH",
                "Selected major does not belong to the specified university.",
            )

        existing = self.session.scalar(
            select(AdmissionTarget).where(
                AdmissionTarget.student_id == student_profile_id,
                AdmissionTarget.university_id == data.university_id,
                AdmissionTarget.major_id == data.major_id,
                AdmissionTarget.target_year == data.target_year,
            )
        )
        if existing:
            raise ApplicationError(
                409,
                "TARGET_ALREADY_EXISTS",
                "Admission target for this university, major, and year already exists.",
            )

        # STRICT PEDAGOGICAL GUARANTEE:
        # Target type (DREAM, TARGET, SAFE) is strictly a personal label chosen by the student.
        # The system does not alter, infer, or evaluate 'safety' here.
        target = AdmissionTarget(
            student_id=student_profile_id,
            university_id=data.university_id,
            major_id=data.major_id,
            target_type=data.target_type,
            target_year=data.target_year,
            priority_order=data.priority_order,
            notes=data.notes,
        )
        self.session.add(target)
        self.session.commit()
        self.session.refresh(target)

        return AdmissionTargetRead(
            id=target.id,
            student_id=target.student_id,
            university_id=target.university_id,
            university_code=university.code,
            university_name=university.name,
            major_id=target.major_id,
            major_code=major.code,
            major_name=major.name,
            target_type=target.target_type,
            target_year=target.target_year,
            priority_order=target.priority_order,
            notes=target.notes,
            created_at=target.created_at,
            updated_at=target.updated_at,
        )

    def delete_student_target(
        self,
        student_profile_id: UUID,
        target_id: UUID,
    ) -> None:
        target = self.session.get(AdmissionTarget, target_id)
        if not target:
            raise ApplicationError(404, "TARGET_NOT_FOUND", "Admission target was not found.")

        if target.student_id != student_profile_id:
            raise ApplicationError(
                403, "FORBIDDEN", "You do not have permission to delete this admission target."
            )

        self.session.delete(target)
        self.session.commit()

    def update_student_target(
        self,
        student_profile_id: UUID,
        target_id: UUID,
        data: AdmissionTargetUpdate,
    ) -> AdmissionTargetRead:
        target = self.session.get(AdmissionTarget, target_id)
        if not target:
            raise ApplicationError(404, "TARGET_NOT_FOUND", "Admission target was not found.")

        if target.student_id != student_profile_id:
            raise ApplicationError(
                403, "FORBIDDEN", "You do not have permission to update this admission target."
            )

        if data.target_type is not None:
            target.target_type = data.target_type
        if data.priority_order is not None:
            target.priority_order = data.priority_order
        if data.notes is not None:
            target.notes = data.notes

        self.session.commit()
        self.session.refresh(target)

        university = self.get_university(target.university_id)
        major = self.get_major(target.major_id)

        return AdmissionTargetRead(
            id=target.id,
            student_id=target.student_id,
            university_id=target.university_id,
            university_code=university.code,
            university_name=university.name,
            major_id=target.major_id,
            major_code=major.code,
            major_name=major.name,
            target_type=target.target_type,
            target_year=target.target_year,
            priority_order=target.priority_order,
            notes=target.notes,
            created_at=target.created_at,
            updated_at=target.updated_at,
        )
