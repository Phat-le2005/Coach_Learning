from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.derivative_activation import (
    DATASET_CODE,
    DerivativeTaxonomyActivationValidator,
)
from app.curriculum.derivative_candidate import DerivativeCurriculumCandidateBuilder
from app.curriculum.import_service import CurriculumImportService
from app.curriculum.models import (
    Chapter,
    Curriculum,
    CurriculumVersion,
    LearningOutcome,
    ProblemType,
    Topic,
    CurriculumImportHistory,
)
from app.questions.group_import_service import (
    CANONICAL_SUBJECT_CODE,
    EXPECTED_DIFFICULTY_DISTRIBUTION,
    LEGACY_SNAPSHOT_SUBJECT_CODE,
    TrustedQuestionGroupImportService,
)
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionGroup,
    QuestionGroupItem,
    QuestionGroupScoringPolicy,
    QuestionGroupType,
    QuestionStatus,
    QuestionType,
)
from app.questions.question_group_promotion import QuestionGroupPromotionValidator
from app.questions.question_group_review_validator import QuestionGroupReviewValidator
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    EXPECTED_RAW_CANDIDATE_SHA256,
)
from app.questions.question_group_visual_assets import QuestionGroupVisualAssetValidator
from app.subjects.models import Subject
from app.users.models import Role, User
from data.seed.identifiers import stable_id


def _seed_subject(
    session: Session,
    subject_code: str = CANONICAL_SUBJECT_CODE,
) -> Subject:
    curriculum = Curriculum(
        id=stable_id("curriculum", "GDPT2018"),
        code="GDPT2018",
        name="GDPT 2018",
    )
    version = CurriculumVersion(
        id=stable_id("curriculum-version", "GDPT2018:GDPT2018_2018"),
        curriculum_id=curriculum.id,
        code="GDPT2018_2018",
        version="2018",
        verified_at=None,
        is_active=True,
    )
    subject = Subject(
        id=stable_id("subject", subject_code),
        curriculum_version_id=version.id,
        code=subject_code,
        name="Grade 12 Mathematics",
        grade_level=12,
        order_index=10,
    )
    session.add_all([curriculum, version, subject])
    session.commit()
    return subject


def _seed_candidate_entities_only(session: Session) -> Subject:
    candidate = DerivativeCurriculumCandidateBuilder().build()
    subject = _seed_subject(session)
    chapters = {
        item.code: Chapter(
            id=stable_id("chapter", f"MATH_G12:{item.code}"),
            subject_id=subject.id,
            code=item.code,
            name=item.name,
            description=item.description,
            order_index=item.order_index,
        )
        for item in candidate.chapters
    }
    session.add_all(chapters.values())
    session.flush()
    topics = {
        item.code: Topic(
            id=stable_id("topic", f"MATH_G12:{item.code}"),
            chapter_id=chapters[item.chapter_code].id,
            code=item.code,
            name=item.name,
            description=item.description,
            order_index=item.order_index,
        )
        for item in candidate.topics
    }
    session.add_all(topics.values())
    session.flush()
    session.add_all(
        ProblemType(
            id=stable_id("problem-type", f"MATH_G12:{item.code}"),
            topic_id=topics[item.topic_code].id,
            code=item.code,
            name=item.name,
            description=item.description,
            order_index=item.order_index,
            default_difficulty=item.default_difficulty,
            is_active=item.is_active,
        )
        for item in candidate.problem_types
    )
    session.add_all(
        Concept(
            id=stable_id("concept", item.code),
            subject_id=subject.id,
            code=item.code,
            name=item.name,
            description=item.description,
            grade_level=item.grade_level,
            order_index=item.order_index,
        )
        for item in candidate.concepts
    )
    session.add_all(
        LearningOutcome(
            id=stable_id("learning-outcome", f"MATH_G12:{item.code}"),
            subject_id=subject.id,
            code=item.code,
            description=item.description,
            grade_level=item.grade_level,
            order_index=item.order_index,
            source_reference=item.source_reference,
        )
        for item in candidate.learning_outcomes
    )
    session.commit()
    return subject


def _import_candidate_taxonomy(session: Session, tmp_path: Path) -> Subject:
    data_root = tmp_path / "curriculum"
    expected = DerivativeTaxonomyActivationValidator.write_import_dataset(data_root)
    result = CurriculumImportService(session, data_root=data_root).import_dataset(
        DATASET_CODE
    )
    assert result.content_hash == expected.content_hash
    history = session.scalar(
        select(CurriculumImportHistory).where(
            CurriculumImportHistory.dataset_code == DATASET_CODE
        )
    )
    assert history is not None
    activation = DerivativeTaxonomyActivationValidator(session).validate()
    assert activation.is_valid, activation.as_dict()
    subject = session.scalar(select(Subject).where(Subject.code == CANONICAL_SUBJECT_CODE))
    assert subject is not None
    return subject


def _actor(
    question_user_factory: Callable[[Role, str], User],
    suffix: str,
) -> User:
    return question_user_factory(Role.ADMIN, f"group-import-{suffix}@example.com")


def test_preview_materializes_exact_draft_groups_and_scoring() -> None:
    preview = TrustedQuestionGroupImportService().preview()
    candidate = DerivativeCurriculumCandidateBuilder().build()
    problem_types = {item.code: item for item in candidate.problem_types}

    assert preview.target_subject_code == "MATH_G12"
    assert preview.snapshot_subject_code == "MATH12"
    assert preview.counts == {
        "groups": 38,
        "children": 152,
        "visual_groups": 8,
        "draft_groups": 38,
        "draft_children": 152,
    }
    assert preview.child_difficulty_distribution == EXPECTED_DIFFICULTY_DISTRIBUTION
    assert "M12_DERIV_GROUP_0012" not in {
        group.external_group_key for group in preview.groups
    }
    assert preview.production_release_eligible == 0
    assert preview.database_import_ready is False
    assert preview.rights_statuses == ("REVIEW_REQUIRED",)

    for group in preview.groups:
        assert group.id == stable_id("question-group", group.external_group_key)
        assert group.subject_code == CANONICAL_SUBJECT_CODE
        assert group.snapshot_subject_code == LEGACY_SNAPSHOT_SUBJECT_CODE
        assert group.status == QuestionStatus.DRAFT.value
        assert group.exam_weight == 1.0
        assert group.production_release_eligible is False
        assert group.difficulty == round(
            sum(child.difficulty for child in group.children) / 4,
            3,
        )
        for child in group.children:
            primary = [link for link in child.problem_types if link.is_primary]
            assert len(primary) == 1
            assert child.difficulty == problem_types[
                primary[0].code
            ].default_difficulty
            assert child.exam_weight == 0.0
            assert child.cognitive_level is None
            assert child.explanation is None
            assert child.id == stable_id("question", child.external_question_key)


def test_confirm_rejects_missing_detailed_taxonomy(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
) -> None:
    _seed_subject(db_session)
    actor = _actor(question_user_factory, "taxonomy-missing")
    service = TrustedQuestionGroupImportService(db_session)
    preview = service.preview()

    with pytest.raises(ApplicationError) as captured:
        service.confirm(preview, actor.id)

    assert captured.value.code == "TRUSTED_GROUP_TAXONOMY_NOT_ACTIVATED"
    assert db_session.scalar(select(func.count()).select_from(Question)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 0


def test_confirm_never_resolves_or_creates_fake_math12_subject(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
) -> None:
    _seed_subject(db_session, LEGACY_SNAPSHOT_SUBJECT_CODE)
    actor = _actor(question_user_factory, "subject-boundary")
    service = TrustedQuestionGroupImportService(db_session)

    with pytest.raises(ApplicationError) as captured:
        service.confirm(service.preview(), actor.id)

    assert captured.value.code == "TRUSTED_GROUP_TAXONOMY_NOT_ACTIVATED"
    assert db_session.scalar(
        select(func.count()).select_from(Subject).where(
            Subject.code == CANONICAL_SUBJECT_CODE
        )
    ) == 0
    assert db_session.scalar(
        select(func.count()).select_from(Subject).where(
            Subject.code == LEGACY_SNAPSHOT_SUBJECT_CODE
        )
    ) == 1


def test_confirm_creates_draft_only_and_is_idempotent(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
    tmp_path: Path,
) -> None:
    subject = _import_candidate_taxonomy(db_session, tmp_path)
    actor = _actor(question_user_factory, "success")
    service = TrustedQuestionGroupImportService(db_session)
    preview = service.preview()

    first = service.confirm(preview, actor.id)

    assert first.created["question_groups"] == 38
    assert first.created["questions"] == 152
    assert first.created["question_group_items"] == 152
    assert len(first.source_lineage) == 38
    assert all(row["rights_status"] == "REVIEW_REQUIRED" for row in first.source_lineage)
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 38
    assert db_session.scalar(select(func.count()).select_from(Question)) == 152
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupItem)) == 152
    assert db_session.scalar(
        select(func.count()).select_from(QuestionGroup).where(
            QuestionGroup.status == QuestionStatus.APPROVED
        )
    ) == 0
    assert db_session.scalar(
        select(func.count()).select_from(Question).where(
            Question.status == QuestionStatus.APPROVED
        )
    ) == 0
    assert db_session.scalar(
        select(func.count()).select_from(Question).where(
            Question.subject_id != subject.id
        )
    ) == 0
    assert db_session.scalar(
        select(func.count()).select_from(Question).where(Question.exam_weight != 0.0)
    ) == 0
    assert db_session.scalar(
        select(func.count()).select_from(QuestionGroup).where(
            QuestionGroup.exam_weight != 1.0
        )
    ) == 0

    second = service.confirm(preview, actor.id)

    assert second.created == {}
    assert second.unchanged["question_groups"] == 38
    assert second.unchanged["questions"] == 152
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 38
    assert db_session.scalar(select(func.count()).select_from(Question)) == 152


def test_existing_question_content_drift_is_rejected(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
    tmp_path: Path,
) -> None:
    _import_candidate_taxonomy(db_session, tmp_path)
    actor = _actor(question_user_factory, "content-drift")
    service = TrustedQuestionGroupImportService(db_session)
    preview = service.preview()
    service.confirm(preview, actor.id)
    question = db_session.get(Question, preview.groups[0].children[0].id)
    assert question is not None
    question.content = question.content + " drift"
    db_session.commit()

    with pytest.raises(ApplicationError) as captured:
        service.confirm(preview, actor.id)

    assert captured.value.code == "TRUSTED_GROUP_IMPORT_DRIFT_CONFLICT"


def test_existing_question_taxonomy_drift_is_rejected(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
    tmp_path: Path,
) -> None:
    _import_candidate_taxonomy(db_session, tmp_path)
    actor = _actor(question_user_factory, "taxonomy-drift")
    service = TrustedQuestionGroupImportService(db_session)
    preview = service.preview()
    service.confirm(preview, actor.id)
    link = db_session.scalar(select(QuestionConcept).limit(1))
    assert link is not None
    link.weight = link.weight / 2
    db_session.commit()

    with pytest.raises(ApplicationError) as captured:
        service.confirm(preview, actor.id)

    assert captured.value.code == "TRUSTED_GROUP_IMPORT_DRIFT_CONFLICT"


def test_existing_child_membership_conflict_blocks_entire_import(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
    tmp_path: Path,
) -> None:
    subject = _import_candidate_taxonomy(db_session, tmp_path)
    actor = _actor(question_user_factory, "membership-conflict")
    service = TrustedQuestionGroupImportService(db_session)
    preview = service.preview()
    child = preview.groups[0].children[0]
    rogue_question = Question(
        id=child.id,
        subject_id=subject.id,
        content="Existing incompatible membership",
        content_hash="0" * 64,
        question_type=QuestionType.TRUE_FALSE,
        difficulty=0.5,
        correct_answer="TRUE",
        explanation=None,
        source_type="TEST_FIXTURE",
        source_reference=None,
        source_year=None,
        cognitive_level=None,
        exam_weight=0.0,
        status=QuestionStatus.DRAFT,
        created_by=actor.id,
    )
    rogue_group = QuestionGroup(
        id=stable_id("question-group", "ROGUE_MEMBERSHIP"),
        subject_id=subject.id,
        content="Rogue membership fixture",
        group_type=QuestionGroupType.TRUE_FALSE_FOUR,
        scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
        difficulty=0.5,
        source_type="TEST_FIXTURE",
        source_reference=None,
        source_year=None,
        cognitive_level=None,
        exam_weight=1.0,
        status=QuestionStatus.DRAFT,
        created_by=actor.id,
    )
    rogue_group.items = [
        QuestionGroupItem(
            id=stable_id("question-group-item", "ROGUE_MEMBERSHIP:a"),
            question_id=child.id,
            label="a",
            order_index=0,
        )
    ]
    db_session.add_all([rogue_question, rogue_group])
    db_session.commit()

    with pytest.raises(ApplicationError) as captured:
        service.confirm(preview, actor.id)

    assert captured.value.code == "TRUSTED_GROUP_IMPORT_DRIFT_CONFLICT"
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 1
    assert db_session.scalar(select(func.count()).select_from(Question)) == 1


def test_confirm_rolls_back_entire_batch_on_late_database_error(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
    tmp_path: Path,
) -> None:
    _import_candidate_taxonomy(db_session, tmp_path)
    actor = _actor(question_user_factory, "rollback")
    service = TrustedQuestionGroupImportService(db_session)
    preview = service.preview()
    fail_group_id: UUID = preview.groups[-1].id

    def fail_last_group(
        mapper: object,
        connection: object,
        target: QuestionGroup,
    ) -> None:
        if target.id == fail_group_id:
            raise RuntimeError("test-only late batch failure")

    event.listen(QuestionGroup, "before_insert", fail_last_group)
    try:
        with pytest.raises(RuntimeError, match="test-only late batch failure"):
            service.confirm(preview, actor.id)
    finally:
        event.remove(QuestionGroup, "before_insert", fail_last_group)

    assert db_session.scalar(select(func.count()).select_from(Question)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupItem)) == 0


def test_upstream_review_promotion_visual_and_raw_invariants_remain() -> None:
    review = QuestionGroupReviewValidator().validate()
    promotion = QuestionGroupPromotionValidator().validate()
    visual = QuestionGroupVisualAssetValidator().validate()
    raw_path = DEFAULT_QUESTION_GROUP_STAGING_PATH.parent / "candidate_questions.json"

    assert review.is_valid
    assert review.counts["structural_groups"] == 67
    assert review.counts["reviewed_groups"] == 67
    assert review.counts["promotion_ready"] == 0
    assert promotion.is_valid
    assert promotion.counts["canonical_snapshot_ready_groups"] == 38
    assert promotion.counts["canonical_snapshot_ready_children"] == 152
    assert visual.is_valid
    assert visual.counts["ready_source_crops"] == 8
    assert visual.counts["blocked_source_visual_missing"] == 1
    import hashlib

    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == (
        EXPECTED_RAW_CANDIDATE_SHA256
    )
