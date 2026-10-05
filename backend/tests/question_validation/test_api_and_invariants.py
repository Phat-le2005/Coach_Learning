from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.question_validation.models import (
    MANUAL_CHECK_TYPES,
    QuestionValidationCandidateStatus,
    QuestionValidationCheckResult,
    QuestionValidationCheckType,
    QuestionValidationRightsDecision,
)
from app.question_validation.promotion import QuestionValidationPromotionService
from app.question_validation.schemas import (
    CandidatePatch,
    ManualReviewInput,
)
from app.question_validation.service import QuestionValidationService
from app.questions.models import Question, QuestionStatus
from app.users.models import Role, User


def test_validation_api_is_admin_only(
    db_client: TestClient,
    validation_setup_factory,
    practice_user_factory: Callable[[Role, str], User],
    practice_bearer: Callable[[User], dict[str, str]],
) -> None:
    setup = validation_setup_factory()
    teacher = practice_user_factory(Role.TEACHER, "validation-teacher@example.com")
    student = practice_user_factory(Role.STUDENT, "validation-student@example.com")
    url = f"/question-validation/acquisition-requests/{setup.request.id}/batches"
    assert db_client.post(url, headers=practice_bearer(teacher)).status_code == 403
    assert db_client.post(url, headers=practice_bearer(student)).status_code == 403
    response = db_client.post(url, headers=practice_bearer(setup.admin))
    assert response.status_code == 201
    assert response.json()["acquisition_request_id"] == str(setup.request.id)


def test_provenance_and_group_boundaries_use_domain_errors(
    db_session: Session, validation_setup_factory, candidate_payload_factory
) -> None:
    setup = validation_setup_factory()
    service = QuestionValidationService(db_session)
    batch = service.create_or_get_batch(setup.request.id, created_by=setup.admin.id)
    payload = candidate_payload_factory(setup)
    with_span_removed = payload.model_copy(update={"spans": []})
    with pytest.raises(ApplicationError) as exc:
        service.create_candidate(batch.id, with_span_removed, created_by=setup.admin.id)
    assert exc.value.code == "QUESTION_VALIDATION_SOURCE_SPAN_REQUIRED"

    grouped = payload.model_copy(update={"group_structure_required": True})
    with pytest.raises(ApplicationError) as exc:
        service.create_candidate(batch.id, grouped, created_by=setup.admin.id)
    assert exc.value.code == "QUESTION_VALIDATION_GROUP_STRUCTURE_REQUIRED"


def test_missing_learning_outcome_and_rights_decision_block_verification(
    db_session: Session, validation_setup_factory, candidate_payload_factory
) -> None:
    setup = validation_setup_factory()
    service = QuestionValidationService(db_session)
    batch = service.create_or_get_batch(setup.request.id, created_by=setup.admin.id)
    payload = candidate_payload_factory(setup, "Missing learning outcome")
    payload = payload.model_copy(
        update={
            "learning_outcomes": [],
            "rights_decision": QuestionValidationRightsDecision.PENDING,
        }
    )
    candidate = service.create_candidate(batch.id, payload, created_by=setup.admin.id)
    candidate = service.run_system_validation(candidate.id)
    taxonomy = next(
        check
        for check in candidate.checks
        if check.check_type == QuestionValidationCheckType.TAXONOMY_INTEGRITY
    )
    assert taxonomy.result == QuestionValidationCheckResult.FAIL
    assert "QUESTION_VALIDATION_LEARNING_OUTCOME_REQUIRED" in taxonomy.details_json["errors"]
    with pytest.raises(ApplicationError) as exc:
        service.record_manual_review(
            candidate.id,
            ManualReviewInput(
                check_type=QuestionValidationCheckType.RIGHTS_REVIEW,
                result=QuestionValidationCheckResult.PASS,
                note="Review attempted without ALLOW_DRAFT",
            ),
            checked_by=setup.admin.id,
        )
    assert exc.value.code == "QUESTION_VALIDATION_RIGHTS_DECISION_REQUIRED"


def test_duplicate_created_after_verification_is_rechecked_at_promotion(
    db_session: Session, validation_setup_factory, candidate_payload_factory
) -> None:
    setup = validation_setup_factory()
    service = QuestionValidationService(db_session)
    batch = service.create_or_get_batch(setup.request.id, created_by=setup.admin.id)
    payload = candidate_payload_factory(setup, "Late duplicate candidate")
    candidate = service.create_candidate(batch.id, payload, created_by=setup.admin.id)
    service.run_system_validation(candidate.id)
    for check_type in MANUAL_CHECK_TYPES:
        service.record_manual_review(
            candidate.id,
            ManualReviewInput(
                check_type=check_type,
                result=QuestionValidationCheckResult.PASS,
                note="Reviewed before concurrent import",
            ),
            checked_by=setup.admin.id,
        )
    assert service.get_candidate(candidate.id).status == QuestionValidationCandidateStatus.VERIFIED
    concurrent = Question(
        subject_id=setup.request.subject_id,
        content=payload.content,
        content_hash="0" * 64,
        question_type=payload.question_type,
        difficulty=0.5,
        correct_answer="B",
        source_type="IMPORT",
        exam_weight=0.5,
        status=QuestionStatus.DRAFT,
        created_by=setup.admin.id,
    )
    db_session.add(concurrent)
    db_session.commit()
    before = db_session.scalar(select(func.count(Question.id)))
    with pytest.raises(ApplicationError) as exc:
        QuestionValidationPromotionService(db_session).promote(
            candidate.id, promoted_by=setup.admin.id
        )
    assert exc.value.code == "QUESTION_VALIDATION_DUPLICATE"
    assert db_session.scalar(select(func.count(Question.id))) == before
    refreshed = service.get_candidate(candidate.id)
    assert refreshed.status == QuestionValidationCandidateStatus.IN_REVIEW
    assert refreshed.promoted_question_id is None


def test_rejected_candidate_is_immutable_without_question_side_effect(
    db_session: Session, validation_setup_factory, candidate_payload_factory
) -> None:
    from app.question_validation.schemas import CandidateRejectInput
    setup = validation_setup_factory()
    service = QuestionValidationService(db_session)
    batch = service.create_or_get_batch(setup.request.id, created_by=setup.admin.id)
    before = db_session.scalar(select(func.count(Question.id)))
    candidate = service.create_candidate(
        batch.id,
        candidate_payload_factory(setup, "Candidate explicitly rejected"),
        created_by=setup.admin.id,
    )
    rejected = service.reject_candidate(
        candidate.id,
        CandidateRejectInput(reason="Source statement is incomplete"),
        updated_by=setup.admin.id,
    )
    assert rejected.status == QuestionValidationCandidateStatus.REJECTED
    with pytest.raises(ApplicationError) as exc:
        service.patch_candidate(
            candidate.id,
            CandidatePatch(expected_revision=1, content="Cannot edit"),
            updated_by=setup.admin.id,
        )
    assert exc.value.code == "QUESTION_VALIDATION_CANDIDATE_REJECTED"
    assert db_session.scalar(select(func.count(Question.id))) == before
