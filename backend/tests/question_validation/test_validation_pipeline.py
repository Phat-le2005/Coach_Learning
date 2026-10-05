import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.question_acquisition.models import (
    QuestionAcquisitionRequestStatus,
    QuestionAcquisitionRightsStatus,
    QuestionAcquisitionStrategy,
)
from app.question_validation.models import (
    MANUAL_CHECK_TYPES,
    QuestionValidationBatchStatus,
    QuestionValidationCandidateStatus,
    QuestionValidationCheckResult,
    QuestionValidationCheckType,
)
from app.question_validation.promotion import QuestionValidationPromotionService
from app.question_validation.schemas import (
    CandidatePatch,
    ManualReviewInput,
)
from app.question_validation.service import QuestionValidationService
from app.question_supply.service import QuestionSupplyGapService
from app.questions.models import Question, QuestionStatus


def test_batch_creation_is_guarded_and_idempotent(
    db_session: Session, validation_setup_factory
) -> None:
    setup = validation_setup_factory()
    service = QuestionValidationService(db_session)
    first = service.create_or_get_batch(setup.request.id, created_by=setup.admin.id)
    second = service.create_or_get_batch(setup.request.id, created_by=setup.admin.id)
    assert first.id == second.id
    assert first.target_candidate_count_snapshot == 1
    assert first.status == QuestionValidationBatchStatus.OPEN

    review_only = validation_setup_factory(
        strategy=QuestionAcquisitionStrategy.REVIEW_EXISTING_PIPELINE,
        external_target=0,
    )
    with pytest.raises(ApplicationError) as exc:
        service.create_or_get_batch(review_only.request.id, created_by=review_only.admin.id)
    assert exc.value.code == "QUESTION_VALIDATION_EXTERNAL_STAGING_NOT_REQUIRED"

    no_target = validation_setup_factory(external_target=0)
    with pytest.raises(ApplicationError) as exc:
        service.create_or_get_batch(no_target.request.id, created_by=no_target.admin.id)
    assert exc.value.code == "QUESTION_VALIDATION_NO_EXTERNAL_TARGET"

    no_artifact = validation_setup_factory(usable_artifact=False)
    with pytest.raises(ApplicationError) as exc:
        service.create_or_get_batch(no_artifact.request.id, created_by=no_artifact.admin.id)
    assert exc.value.code == "QUESTION_VALIDATION_NO_USABLE_ARTIFACT"

    not_ready = validation_setup_factory(
        request_status=QuestionAcquisitionRequestStatus.STAGED
    )
    with pytest.raises(ApplicationError) as exc:
        service.create_or_get_batch(not_ready.request.id, created_by=not_ready.admin.id)
    assert exc.value.code == "QUESTION_VALIDATION_REQUEST_NOT_READY"


def test_source_excerpt_is_derived_and_revision_invalidates_checks(
    db_session: Session, validation_setup_factory, candidate_payload_factory
) -> None:
    setup = validation_setup_factory()
    service = QuestionValidationService(db_session)
    batch = service.create_or_get_batch(setup.request.id, created_by=setup.admin.id)
    before = db_session.scalar(select(func.count(Question.id)))
    candidate = service.create_candidate(
        batch.id, candidate_payload_factory(setup), created_by=setup.admin.id
    )
    assert candidate.revision == 1
    assert candidate.spans[0].excerpt == setup.page.text
    assert candidate.spans[0].excerpt_sha256 == hashlib.sha256(
        setup.page.text.encode()
    ).hexdigest()
    assert db_session.scalar(select(func.count(Question.id))) == before

    service.run_system_validation(candidate.id)
    for check_type in MANUAL_CHECK_TYPES:
        service.record_manual_review(
            candidate.id,
            ManualReviewInput(
                check_type=check_type,
                result=QuestionValidationCheckResult.PASS,
                note=f"Reviewed {check_type.value}",
            ),
            checked_by=setup.admin.id,
        )
    candidate = service.get_candidate(candidate.id)
    assert candidate.status == QuestionValidationCandidateStatus.VERIFIED
    assert candidate.batch.status == QuestionValidationBatchStatus.READY_FOR_PROMOTION

    changed = service.patch_candidate(
        candidate.id,
        CandidatePatch(expected_revision=1, content="Reviewed revision two"),
        updated_by=setup.admin.id,
    )
    assert changed.revision == 2
    assert changed.status == QuestionValidationCandidateStatus.IN_REVIEW
    assert all(check.candidate_revision == 1 for check in changed.checks)
    with pytest.raises(ApplicationError) as exc:
        service.patch_candidate(
            candidate.id,
            CandidatePatch(expected_revision=1, explanation="stale edit"),
            updated_by=setup.admin.id,
        )
    assert exc.value.code == "QUESTION_VALIDATION_REVISION_CONFLICT"


def test_all_gates_promote_exact_draft_and_reassess_supply(
    db_session: Session, validation_setup_factory, candidate_payload_factory
) -> None:
    setup = validation_setup_factory()
    service = QuestionValidationService(db_session)
    QuestionSupplyGapService(db_session).reassess_gap(setup.gap.id)
    db_session.refresh(setup.gap)
    approved_before = setup.gap.approved_eligible_count
    batch = service.create_or_get_batch(setup.request.id, created_by=setup.admin.id)
    payload = candidate_payload_factory(setup, "Unique promotion candidate")
    candidate = service.create_candidate(batch.id, payload, created_by=setup.admin.id)
    service.run_system_validation(candidate.id)
    assert service.get_candidate(candidate.id).status == QuestionValidationCandidateStatus.IN_REVIEW
    for check_type in MANUAL_CHECK_TYPES:
        service.record_manual_review(
            candidate.id,
            ManualReviewInput(
                check_type=check_type,
                result=QuestionValidationCheckResult.PASS,
                note="Explicit reviewed decision",
            ),
            checked_by=setup.admin.id,
        )
    promoted, question = QuestionValidationPromotionService(db_session).promote(
        candidate.id, promoted_by=setup.admin.id
    )
    assert promoted.status == QuestionValidationCandidateStatus.PROMOTED
    assert question.status == QuestionStatus.DRAFT
    assert question.content == payload.content
    assert question.source_type == "ACQUISITION"
    assert question.source_reference == f"acquisition:candidate:{candidate.id}"
    assert question.correct_answer == payload.correct_answer
    assert [(x.label, x.content) for x in question.options] == [("A", "Negative"), ("B", "Positive")]
    assert {x.concept_id for x in question.concept_links} == {payload.concepts[0].concept_id}
    assert {x.problem_type_id for x in question.problem_type_links} == {payload.problem_types[0].problem_type_id}
    assert {x.learning_outcome_id for x in question.learning_outcome_links} == {payload.learning_outcomes[0].learning_outcome_id}

    same_candidate, same_question = QuestionValidationPromotionService(db_session).promote(
        candidate.id, promoted_by=setup.admin.id
    )
    assert same_candidate.id == promoted.id
    assert same_question.id == question.id
    assert db_session.scalar(
        select(func.count(Question.id)).where(Question.id == question.id)
    ) == 1
    db_session.refresh(setup.gap)
    assert setup.gap.pipeline_candidate_count >= 1
    assert setup.gap.approved_eligible_count == approved_before
    assert setup.gap.status != "RESOLVED"
    db_session.refresh(batch)
    assert batch.status == QuestionValidationBatchStatus.COMPLETED

    with pytest.raises(ApplicationError) as exc:
        service.create_or_get_batch(setup.request.id, created_by=setup.admin.id)
    assert exc.value.code == "QUESTION_VALIDATION_TARGET_ALREADY_SATISFIED"


def test_visual_duplicate_and_blocked_source_prevent_promotion(
    db_session: Session, validation_setup_factory, candidate_payload_factory
) -> None:
    setup = validation_setup_factory(external_target=3)
    service = QuestionValidationService(db_session)
    batch = service.create_or_get_batch(setup.request.id, created_by=setup.admin.id)
    visual_payload = candidate_payload_factory(setup, "Visual-dependent question")
    visual_payload = visual_payload.model_copy(update={"visual_required": True})
    visual = service.create_candidate(batch.id, visual_payload, created_by=setup.admin.id)
    visual = service.run_system_validation(visual.id)
    visual_check = next(
        check
        for check in visual.checks
        if check.candidate_revision == visual.revision
        and check.check_type == QuestionValidationCheckType.VISUAL_INTEGRITY
    )
    assert visual_check.result == QuestionValidationCheckResult.FAIL

    payload_subject = setup.request.subject_id
    existing = Question(
        subject_id=payload_subject,
        content="Production duplicate text",
        content_hash="0" * 64,
        question_type=visual_payload.question_type,
        difficulty=0.5,
        correct_answer="B",
        source_type="TEST",
        exam_weight=0.5,
        status=QuestionStatus.DRAFT,
        created_by=setup.admin.id,
    )
    db_session.add(existing)
    db_session.commit()
    duplicate = service.create_candidate(
        batch.id,
        candidate_payload_factory(setup, "Production duplicate text"),
        created_by=setup.admin.id,
    )
    duplicate = service.run_system_validation(duplicate.id)
    duplicate_check = next(
        check for check in duplicate.checks if check.check_type == QuestionValidationCheckType.DUPLICATE
    )
    assert duplicate_check.result == QuestionValidationCheckResult.FAIL
    assert payload_subject == setup.request.subject_id

    ready = service.create_candidate(
        batch.id,
        candidate_payload_factory(setup, "Blocked after review"),
        created_by=setup.admin.id,
    )
    service.run_system_validation(ready.id)
    for check_type in MANUAL_CHECK_TYPES:
        service.record_manual_review(
            ready.id,
            ManualReviewInput(check_type=check_type, result=QuestionValidationCheckResult.PASS, note="Reviewed"),
            checked_by=setup.admin.id,
        )
    setup.source.rights_status = QuestionAcquisitionRightsStatus.BLOCKED
    db_session.commit()
    with pytest.raises(ApplicationError) as exc:
        QuestionValidationPromotionService(db_session).promote(ready.id, promoted_by=setup.admin.id)
    assert exc.value.code == "QUESTION_VALIDATION_SOURCE_BLOCKED"
