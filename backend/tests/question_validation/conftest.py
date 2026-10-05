from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.question_acquisition.models import (
    QuestionAcquisitionArtifact,
    QuestionAcquisitionExtractionStatus,
    QuestionAcquisitionPage,
    QuestionAcquisitionRequest,
    QuestionAcquisitionRequestStatus,
    QuestionAcquisitionRightsStatus,
    QuestionAcquisitionSource,
    QuestionAcquisitionSourceArtifact,
    QuestionAcquisitionSourceKind,
    QuestionAcquisitionSourceStatus,
    QuestionAcquisitionDiscoveryMethod,
    QuestionAcquisitionStrategy,
)
from app.question_supply.models import (
    QuestionSupplyGap,
    QuestionSupplyReasonCode,
    QuestionSupplySeverity,
    QuestionSupplyStatus,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.question_validation.models import QuestionValidationRightsDecision
from app.question_validation.schemas import (
    CandidateConceptInput,
    CandidateCreate,
    CandidateLearningOutcomeInput,
    CandidateOptionInput,
    CandidateProblemTypeInput,
    CandidateSpanInput,
)
from app.questions.models import QuestionType
from app.users.models import Role, User
from tests.practice.conftest import (
    PracticeContent,
    practice_bearer,
    practice_content,
    practice_user_factory,
)

__all__ = [
    "PracticeContent",
    "practice_bearer",
    "practice_content",
    "practice_user_factory",
]


@dataclass(frozen=True)
class ValidationSetup:
    gap: QuestionSupplyGap
    request: QuestionAcquisitionRequest
    source: QuestionAcquisitionSource
    artifact: QuestionAcquisitionArtifact
    page: QuestionAcquisitionPage
    admin: User


@pytest.fixture
def validation_setup_factory(
    db_session: Session,
    practice_content: PracticeContent,
    practice_user_factory: Callable[[Role, str], User],
) -> Callable[..., ValidationSetup]:
    def create(
        *,
        external_target: int = 1,
        strategy: QuestionAcquisitionStrategy = QuestionAcquisitionStrategy.EXTERNAL_SOURCE_REQUIRED,
        request_status: QuestionAcquisitionRequestStatus = QuestionAcquisitionRequestStatus.READY_FOR_REVIEW,
        usable_artifact: bool = True,
    ) -> ValidationSetup:
        suffix = uuid4().hex
        admin = practice_user_factory(Role.ADMIN, f"validation-{suffix}@example.com")
        now = datetime.now(timezone.utc)
        gap = QuestionSupplyGap(
            signature=hashlib.sha256(suffix.encode()).hexdigest(),
            subject_id=practice_content.subject.id,
            use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
            target_type=QuestionSupplyTargetType.CONCEPT,
            concept_id=practice_content.concept.id,
            difficulty_min=0.0,
            difficulty_max=1.0,
            desired_difficulty=0.5,
            minimum_required_count=10,
            preferred_count=10,
            approved_eligible_count=0,
            approved_in_band_count=0,
            pipeline_candidate_count=0,
            pipeline_runtime_eligible_count=0,
            severity=QuestionSupplySeverity.HIGH,
            status=QuestionSupplyStatus.IN_PROGRESS,
            reason_code=QuestionSupplyReasonCode.NO_APPROVED_TARGET_QUESTIONS,
            demand_count=1,
            first_observed_at=now,
            last_observed_at=now,
            last_assessed_at=now,
        )
        db_session.add(gap)
        db_session.flush()
        request = QuestionAcquisitionRequest(
            gap_id=gap.id,
            attempt_index=1,
            strategy=strategy,
            status=request_status,
            subject_id=practice_content.subject.id,
            use_case=gap.use_case,
            target_type=gap.target_type,
            concept_id=gap.concept_id,
            difficulty_min=0.0,
            difficulty_max=1.0,
            desired_difficulty=0.5,
            minimum_required_count=10,
            preferred_count=10,
            shortage_reason_code=gap.reason_code,
            required_new_candidate_count=max(external_target, 0),
            external_candidate_target_count=external_target,
            created_by=admin.id,
        )
        db_session.add(request)
        db_session.flush()
        source = QuestionAcquisitionSource(
            request_id=request.id,
            source_kind=QuestionAcquisitionSourceKind.MANUAL_PDF_UPLOAD,
            discovery_method=QuestionAcquisitionDiscoveryMethod.ADMIN_UPLOAD,
            title="Reviewed source",
            source_year=2025,
            rights_status=QuestionAcquisitionRightsStatus.REVIEW_REQUIRED,
            status=QuestionAcquisitionSourceStatus.FETCHED,
            provenance_note="Validation test source",
            registered_by=admin.id,
        )
        text = "Question source: Which interval is increasing? A. Negative B. Positive"
        artifact = QuestionAcquisitionArtifact(
            sha256=hashlib.sha256(suffix.encode()).hexdigest(),
            mime_type="application/pdf",
            file_size_bytes=100,
            page_count=1,
            storage_key=f"test/{suffix}.pdf",
            extraction_status=(
                QuestionAcquisitionExtractionStatus.COMPLETE
                if usable_artifact
                else QuestionAcquisitionExtractionStatus.FAILED
            ),
        )
        db_session.add_all([source, artifact])
        db_session.flush()
        db_session.add(
            QuestionAcquisitionSourceArtifact(source_id=source.id, artifact_id=artifact.id)
        )
        page = QuestionAcquisitionPage(
            artifact_id=artifact.id,
            page_number=1,
            text=text,
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            char_count=len(text),
        )
        db_session.add(page)
        db_session.commit()
        return ValidationSetup(gap, request, source, artifact, page, admin)

    return create


@pytest.fixture
def candidate_payload_factory(
    practice_content: PracticeContent,
) -> Callable[[ValidationSetup, str], CandidateCreate]:
    def create(setup: ValidationSetup, content: str = "A new reviewed acquisition question") -> CandidateCreate:
        return CandidateCreate(
            source_id=setup.source.id,
            content=content,
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=0.5,
            correct_answer="B",
            explanation="Reviewed explanation",
            exam_weight=0.5,
            source_year=2025,
            visual_required=False,
            rights_decision=QuestionValidationRightsDecision.ALLOW_DRAFT,
            spans=[
                CandidateSpanInput(
                    page_id=setup.page.id,
                    order_index=0,
                    start_char=0,
                    end_char=len(setup.page.text),
                )
            ],
            options=[
                CandidateOptionInput(label="A", content="Negative", order_index=0),
                CandidateOptionInput(label="B", content="Positive", order_index=1),
            ],
            concepts=[CandidateConceptInput(concept_id=practice_content.concept.id, weight=1.0)],
            problem_types=[
                CandidateProblemTypeInput(
                    problem_type_id=practice_content.problem_type.id,
                    weight=1.0,
                    is_primary=True,
                )
            ],
            learning_outcomes=[
                CandidateLearningOutcomeInput(
                    learning_outcome_id=practice_content.learning_outcome.id,
                    weight=1.0,
                )
            ],
        )

    return create
