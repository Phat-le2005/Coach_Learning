from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.derivative_candidate import (
    DEFAULT_PRODUCTION_BRIDGE_ROOT,
    DerivativeCurriculumCandidate,
    DerivativeCurriculumCandidateValidator,
)
from app.curriculum.derivative_activation import (
    DerivativeTaxonomyActivationValidator,
)
from app.curriculum.models import (
    Chapter,
    CurriculumVersion,
    LearningOutcome,
    ProblemType,
    Topic,
)
from app.questions.group_import_schemas import (
    GroupImportConceptLink,
    GroupImportOutcomeLink,
    GroupImportProblemTypeLink,
    TrustedGroupCandidate,
    TrustedGroupChildCandidate,
    TrustedGroupImportPreview,
    TrustedGroupImportResult,
)
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionGroup,
    QuestionGroupItem,
    QuestionGroupScoringPolicy,
    QuestionGroupType,
    QuestionLearningOutcome,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.questions.question_group_promotion import QuestionGroupPromotionValidator
from app.questions.question_group_staging import EXPECTED_RAW_CANDIDATE_SHA256
from app.questions.question_group_visual_assets import QuestionGroupVisualAssetValidator
from app.subjects.models import Subject
from app.users.models import User
from data.seed.identifiers import stable_id


logger = logging.getLogger(__name__)

CANONICAL_SUBJECT_CODE = "MATH_G12"
LEGACY_SNAPSHOT_SUBJECT_CODE = "MATH12"
EXPECTED_DIFFICULTY_DISTRIBUTION = {
    "0.25": 11,
    "0.30": 14,
    "0.35": 4,
    "0.45": 24,
    "0.50": 69,
    "0.55": 16,
    "0.60": 2,
    "0.65": 5,
    "0.70": 4,
    "0.75": 3,
}


class TrustedQuestionGroupImportService:
    """Preview and atomically import reviewed groups as internal DRAFT data."""

    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def preview(
        self,
        bridge_root: Path = DEFAULT_PRODUCTION_BRIDGE_ROOT,
    ) -> TrustedGroupImportPreview:
        bridge_root = bridge_root.resolve()
        candidate_report = DerivativeCurriculumCandidateValidator().validate(
            bridge_root=bridge_root
        )
        if not candidate_report.is_valid or candidate_report.candidate is None:
            raise ApplicationError(
                422,
                "DERIVATIVE_CURRICULUM_CANDIDATE_INVALID",
                "The derivative curriculum candidate did not pass validation.",
            )
        promotion_report = QuestionGroupPromotionValidator().validate()
        if not promotion_report.is_valid:
            raise ApplicationError(
                422,
                "QUESTION_GROUP_PROMOTION_INVALID",
                "QuestionGroup promotion preflight did not pass validation.",
            )
        visual_report = QuestionGroupVisualAssetValidator().validate()
        if not visual_report.is_valid:
            raise ApplicationError(
                422,
                "QUESTION_GROUP_VISUAL_REGISTRY_INVALID",
                "QuestionGroup visual registry did not pass validation.",
            )

        contract = self._load_object(
            bridge_root / "trusted_group_import_contract.json"
        )
        scoring_policy = self._load_object(
            bridge_root / "scoring_metadata_policy.json"
        )
        self._validate_subject_contract(contract)
        groups = self._materialize_groups(
            promotion_report.snapshot,
            candidate_report.candidate,
        )
        distribution = self._difficulty_distribution(groups)
        expected_distribution = scoring_policy.get("difficulty", {}).get(
            "candidate_distribution"
        )
        if distribution != expected_distribution or distribution != (
            EXPECTED_DIFFICULTY_DISTRIBUTION
        ):
            raise ApplicationError(
                422,
                "GROUP_IMPORT_DIFFICULTY_DISTRIBUTION_MISMATCH",
                "Derived child difficulty distribution does not match reviewed policy.",
            )
        counts = {
            "groups": len(groups),
            "children": sum(len(group.children) for group in groups),
            "visual_groups": sum(group.visual_asset_id is not None for group in groups),
            "draft_groups": sum(group.status == QuestionStatus.DRAFT.value for group in groups),
            "draft_children": sum(
                child.question_type == QuestionType.TRUE_FALSE.value
                for group in groups
                for child in group.children
            ),
        }
        if counts != {
            "groups": 38,
            "children": 152,
            "visual_groups": 8,
            "draft_groups": 38,
            "draft_children": 152,
        }:
            raise ApplicationError(
                422,
                "GROUP_IMPORT_PREVIEW_COUNTS_MISMATCH",
                f"Unexpected trusted group preview counts: {counts}.",
            )
        return TrustedGroupImportPreview(
            dataset_code="DATA-MATH12-012",
            target_subject_code=CANONICAL_SUBJECT_CODE,
            snapshot_subject_code=LEGACY_SNAPSHOT_SUBJECT_CODE,
            curriculum_candidate_version="1.2.0",
            curriculum_candidate_hash=candidate_report.content_hash,
            promotion_snapshot_hash=promotion_report.snapshot_sha256,
            raw_candidate_sha256=EXPECTED_RAW_CANDIDATE_SHA256,
            groups=tuple(groups),
            counts=counts,
            child_difficulty_distribution=distribution,
            rights_statuses=tuple(
                sorted({group.rights_status for group in groups})
            ),
            production_release_eligible=0,
            database_import_ready=False,
        )

    def confirm(
        self,
        preview: TrustedGroupImportPreview,
        created_by: UUID,
        *,
        commit: bool = True,
    ) -> TrustedGroupImportResult:
        if self.session is None:
            raise RuntimeError("A database session is required for confirm().")
        current = self.preview()
        if preview != current:
            raise ApplicationError(
                409,
                "TRUSTED_GROUP_PREVIEW_STALE",
                "Import preview no longer matches reviewed source materialization.",
            )
        if current.target_subject_code != CANONICAL_SUBJECT_CODE:
            raise ApplicationError(
                422,
                "TRUSTED_GROUP_SUBJECT_IDENTITY_INVALID",
                "Trusted group import must target MATH_G12.",
            )
        created: Counter[str] = Counter()
        unchanged: Counter[str] = Counter()
        try:
            if self.session.get(User, created_by) is None:
                raise ApplicationError(
                    404,
                    "TRUSTED_GROUP_IMPORT_ACTOR_NOT_FOUND",
                    "Import actor was not found.",
                )
            self._lock()
            activation = DerivativeTaxonomyActivationValidator(self.session).validate()
            if not activation.is_valid:
                issue_codes = sorted({issue.code for issue in activation.errors})
                raise ApplicationError(
                    409,
                    "TRUSTED_GROUP_TAXONOMY_NOT_ACTIVATED",
                    "Canonical derivative taxonomy activation proof failed: "
                    + ", ".join(issue_codes[:8]),
                )
            subject, problem_types, concepts, outcomes = self._resolve_taxonomy(
                current
            )
            self._preflight_existing(
                current, subject, problem_types, concepts, outcomes
            )
            existing_group_ids = set(
                self.session.scalars(
                    select(QuestionGroup.id).where(
                        QuestionGroup.id.in_([group.id for group in current.groups])
                    )
                )
            )
            for group in current.groups:
                if group.id in existing_group_ids:
                    unchanged["question_groups"] += 1
                    unchanged["questions"] += 4
                    unchanged["question_group_items"] += 4
                    unchanged["taxonomy_links"] += sum(
                        len(child.problem_types)
                        + len(child.concepts)
                        + len(child.learning_outcomes)
                        for child in group.children
                    )
                    continue
                questions = []
                for child in group.children:
                    question = Question(
                        id=child.id,
                        subject_id=subject.id,
                        content=child.content,
                        content_hash="0" * 64,
                        question_type=QuestionType.TRUE_FALSE,
                        difficulty=child.difficulty,
                        correct_answer=child.correct_answer,
                        explanation=None,
                        source_type=str(group.source_lineage["source_code"]),
                        source_reference=str(
                            group.source_lineage["source_evidence_id"]
                        ),
                        source_year=None,
                        cognitive_level=None,
                        exam_weight=0.0,
                        status=QuestionStatus.DRAFT,
                        created_by=created_by,
                    )
                    question.problem_type_links = [
                        QuestionProblemType(
                            problem_type_id=problem_types[link.code].id,
                            weight=link.weight,
                            is_primary=link.is_primary,
                        )
                        for link in child.problem_types
                    ]
                    question.concept_links = [
                        QuestionConcept(
                            concept_id=concepts[link.code].id,
                            weight=link.weight,
                        )
                        for link in child.concepts
                    ]
                    question.learning_outcome_links = [
                        QuestionLearningOutcome(
                            learning_outcome_id=outcomes[link.code].id,
                            weight=link.weight,
                        )
                        for link in child.learning_outcomes
                    ]
                    questions.append((child, question))
                    self.session.add(question)
                    created["questions"] += 1
                    created["taxonomy_links"] += (
                        len(child.problem_types)
                        + len(child.concepts)
                        + len(child.learning_outcomes)
                    )
                question_group = QuestionGroup(
                    id=group.id,
                    subject_id=subject.id,
                    content=group.content,
                    group_type=QuestionGroupType.TRUE_FALSE_FOUR,
                    scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
                    difficulty=group.difficulty,
                    source_type=str(group.source_lineage["source_code"]),
                    source_reference=str(
                        group.source_lineage["source_evidence_id"]
                    ),
                    source_year=None,
                    cognitive_level=None,
                    exam_weight=1.0,
                    status=QuestionStatus.DRAFT,
                    created_by=created_by,
                )
                question_group.items = [
                    QuestionGroupItem(
                        id=stable_id(
                            "question-group-item", child.external_question_key
                        ),
                        question_id=question.id,
                        label=child.label,
                        order_index=child.order_index,
                    )
                    for child, question in questions
                ]
                self.session.add(question_group)
                created["question_groups"] += 1
                created["question_group_items"] += 4
            self.session.flush()
            if commit:
                self.session.commit()
        except ApplicationError:
            self.session.rollback()
            raise
        except IntegrityError as error:
            self.session.rollback()
            raise ApplicationError(
                409,
                "TRUSTED_GROUP_IMPORT_CONFLICT",
                "Trusted QuestionGroup import hit a database constraint conflict.",
            ) from error
        except Exception:
            self.session.rollback()
            raise

        lineage = tuple(
            {
                "external_group_key": group.external_group_key,
                "group_id": str(group.id),
                "source": group.source_lineage,
                "visual_asset_id": group.visual_asset_id,
                "rights_status": group.rights_status,
            }
            for group in current.groups
        )
        logger.info(
            "Trusted QuestionGroup import completed (groups=%s, children=%s)",
            len(current.groups),
            current.counts["children"],
        )
        return TrustedGroupImportResult(
            preview=current,
            created=dict(created),
            unchanged=dict(unchanged),
            source_lineage=lineage,
        )

    def _materialize_groups(
        self,
        snapshot: tuple[dict[str, Any], ...],
        candidate: DerivativeCurriculumCandidate,
    ) -> list[TrustedGroupCandidate]:
        problem_types = {item.code: item for item in candidate.problem_types}
        groups: list[TrustedGroupCandidate] = []
        for source_group in snapshot:
            snapshot_subject = source_group.get("subject_code")
            if snapshot_subject != LEGACY_SNAPSHOT_SUBJECT_CODE:
                raise ApplicationError(
                    422,
                    "TRUSTED_GROUP_SNAPSHOT_SUBJECT_INVALID",
                    "DATA-MATH12-011 snapshot must retain historical subject MATH12.",
                )
            external_group_key = str(source_group["external_group_key"])
            if external_group_key == "M12_DERIV_GROUP_0012":
                raise ApplicationError(
                    422,
                    "TRUSTED_GROUP_BLOCKED_VISUAL_INCLUDED",
                    "M12_DERIV_GROUP_0012 cannot enter trusted import preview.",
                )
            children = []
            for source_child in source_group["children"]:
                primary = [
                    link
                    for link in source_child["problem_types"]
                    if link.get("is_primary") is True
                ]
                if len(primary) != 1:
                    raise ApplicationError(
                        422,
                        "TRUSTED_GROUP_PRIMARY_PROBLEM_TYPE_INVALID",
                        f"{source_child['external_question_key']} must have one primary ProblemType.",
                    )
                primary_code = str(primary[0]["code"])
                problem_type = problem_types.get(primary_code)
                if problem_type is None or problem_type.default_difficulty is None:
                    raise ApplicationError(
                        422,
                        "TRUSTED_GROUP_DIFFICULTY_NOT_RESOLVED",
                        f"No reviewed default difficulty for {primary_code}.",
                    )
                external_question_key = str(source_child["external_question_key"])
                children.append(
                    TrustedGroupChildCandidate(
                        id=stable_id("question", external_question_key),
                        external_question_key=external_question_key,
                        label=str(source_child["label"]),
                        order_index=int(source_child["order_index"]),
                        question_type=QuestionType.TRUE_FALSE.value,
                        content=str(source_child["content"]),
                        correct_answer=str(source_child["correct_answer"]),
                        difficulty=problem_type.default_difficulty,
                        exam_weight=0.0,
                        cognitive_level=None,
                        explanation=None,
                        problem_types=tuple(
                            GroupImportProblemTypeLink.model_validate(link)
                            for link in source_child["problem_types"]
                        ),
                        concepts=tuple(
                            GroupImportConceptLink.model_validate(link)
                            for link in source_child["concepts"]
                        ),
                        learning_outcomes=tuple(
                            GroupImportOutcomeLink.model_validate(link)
                            for link in source_child["learning_outcomes"]
                        ),
                        taxonomy_basis=str(source_child["taxonomy_basis"]),
                    )
                )
            difficulty = round(
                sum(child.difficulty for child in children) / len(children), 3
            )
            source_lineage = dict(source_group["source"])
            groups.append(
                TrustedGroupCandidate(
                    id=stable_id("question-group", external_group_key),
                    external_group_key=external_group_key,
                    subject_code=CANONICAL_SUBJECT_CODE,
                    snapshot_subject_code=LEGACY_SNAPSHOT_SUBJECT_CODE,
                    group_type=QuestionGroupType.TRUE_FALSE_FOUR.value,
                    scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE.value,
                    content=str(source_group["content"]),
                    difficulty=difficulty,
                    exam_weight=1.0,
                    cognitive_level=None,
                    status=QuestionStatus.DRAFT.value,
                    visual_asset_id=source_group.get("visual_asset_id"),
                    source_lineage=source_lineage,
                    review_lineage=dict(source_group["review_lineage"]),
                    rights_status=str(source_lineage["rights_status"]),
                    children=tuple(children),
                    production_release_eligible=False,
                )
            )
        return sorted(groups, key=lambda group: group.external_group_key)

    def _resolve_taxonomy(
        self,
        preview: TrustedGroupImportPreview,
    ) -> tuple[
        Subject,
        dict[str, ProblemType],
        dict[str, Concept],
        dict[str, LearningOutcome],
    ]:
        assert self.session is not None
        subjects = list(
            self.session.scalars(
                select(Subject)
                .join(
                    CurriculumVersion,
                    Subject.curriculum_version_id == CurriculumVersion.id,
                )
                .where(
                    Subject.code == CANONICAL_SUBJECT_CODE,
                    Subject.grade_level == 12,
                    CurriculumVersion.code == "GDPT2018_2018",
                )
            )
        )
        if len(subjects) != 1:
            raise ApplicationError(
                409,
                "TRUSTED_GROUP_TAXONOMY_NOT_READY",
                "Canonical Subject MATH_G12 for GDPT2018_2018 is not ready.",
            )
        subject = subjects[0]
        problem_codes = {
            link.code
            for group in preview.groups
            for child in group.children
            for link in child.problem_types
        }
        concept_codes = {
            link.code
            for group in preview.groups
            for child in group.children
            for link in child.concepts
        }
        outcome_codes = {
            link.code
            for group in preview.groups
            for child in group.children
            for link in child.learning_outcomes
        }
        problem_rows = self.session.execute(
            select(ProblemType, Topic.code)
            .join(Topic, ProblemType.topic_id == Topic.id)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(
                Chapter.subject_id == subject.id,
                ProblemType.code.in_(problem_codes),
            )
        ).all()
        problem_types = {problem.code: problem for problem, _ in problem_rows}
        problem_topic_codes = {
            problem.code: topic_code for problem, topic_code in problem_rows
        }
        concepts = {
            concept.code: concept
            for concept in self.session.scalars(
                select(Concept).where(
                    Concept.subject_id == subject.id,
                    Concept.code.in_(concept_codes),
                )
            )
        }
        outcomes = {
            outcome.code: outcome
            for outcome in self.session.scalars(
                select(LearningOutcome).where(
                    LearningOutcome.subject_id == subject.id,
                    LearningOutcome.code.in_(outcome_codes),
                )
            )
        }
        missing = {
            "problem_types": sorted(problem_codes - set(problem_types)),
            "concepts": sorted(concept_codes - set(concepts)),
            "learning_outcomes": sorted(outcome_codes - set(outcomes)),
        }
        if any(missing.values()):
            raise ApplicationError(
                409,
                "TRUSTED_GROUP_TAXONOMY_NOT_READY",
                "Detailed derivative taxonomy is not ready in the database: "
                + json.dumps(missing, ensure_ascii=False, sort_keys=True),
            )
        candidate_report = DerivativeCurriculumCandidateValidator().validate()
        if not candidate_report.is_valid or candidate_report.candidate is None:
            raise ApplicationError(
                409,
                "TRUSTED_GROUP_TAXONOMY_NOT_READY",
                "Derivative taxonomy candidate is invalid.",
            )
        candidate_problem_types = {
            item.code: item for item in candidate_report.candidate.problem_types
        }
        candidate_concepts = {
            item.code: item for item in candidate_report.candidate.concepts
        }
        candidate_outcomes = {
            item.code: item
            for item in candidate_report.candidate.learning_outcomes
        }
        mismatched_problems = sorted(
            code
            for code, problem in problem_types.items()
            if (
                problem_topic_codes[code] != candidate_problem_types[code].topic_code
                or problem.name != candidate_problem_types[code].name
                or problem.description != candidate_problem_types[code].description
                or problem.order_index != candidate_problem_types[code].order_index
                or problem.default_difficulty
                != candidate_problem_types[code].default_difficulty
                or problem.is_active != candidate_problem_types[code].is_active
            )
        )
        mismatched_concepts = sorted(
            code
            for code, concept in concepts.items()
            if (
                concept.name != candidate_concepts[code].name
                or concept.description != candidate_concepts[code].description
                or concept.grade_level != candidate_concepts[code].grade_level
                or concept.order_index != candidate_concepts[code].order_index
            )
        )
        mismatched_outcomes = sorted(
            code
            for code, outcome in outcomes.items()
            if (
                outcome.description != candidate_outcomes[code].description
                or outcome.grade_level != candidate_outcomes[code].grade_level
                or outcome.order_index != candidate_outcomes[code].order_index
                or outcome.source_reference
                != candidate_outcomes[code].source_reference
            )
        )
        if mismatched_problems or mismatched_concepts or mismatched_outcomes:
            raise ApplicationError(
                409,
                "TRUSTED_GROUP_TAXONOMY_NOT_READY",
                "Database taxonomy differs from reviewed candidate: "
                + json.dumps(
                    {
                        "problem_types": mismatched_problems,
                        "concepts": mismatched_concepts,
                        "learning_outcomes": mismatched_outcomes,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        return subject, problem_types, concepts, outcomes

    def _preflight_existing(
        self,
        preview: TrustedGroupImportPreview,
        subject: Subject,
        problem_types: dict[str, ProblemType],
        concepts: dict[str, Concept],
        outcomes: dict[str, LearningOutcome],
    ) -> None:
        assert self.session is not None
        child_candidates = {
            child.id: (group, child)
            for group in preview.groups
            for child in group.children
        }
        existing_questions = {
            question.id: question
            for question in self.session.scalars(
                select(Question)
                .options(
                    selectinload(Question.problem_type_links),
                    selectinload(Question.concept_links),
                    selectinload(Question.learning_outcome_links),
                )
                .where(Question.id.in_(child_candidates))
            )
        }
        existing_groups = {
            group.id: group
            for group in self.session.scalars(
                select(QuestionGroup)
                .options(
                    selectinload(QuestionGroup.items).selectinload(
                        QuestionGroupItem.question
                    )
                )
                .where(QuestionGroup.id.in_([group.id for group in preview.groups]))
            )
        }
        memberships = {
            item.question_id: item
            for item in self.session.scalars(
                select(QuestionGroupItem).where(
                    QuestionGroupItem.question_id.in_(child_candidates)
                )
            )
        }

        for group in preview.groups:
            existing_group = existing_groups.get(group.id)
            existing_children = [
                existing_questions.get(child.id) for child in group.children
            ]
            if existing_group is None:
                if any(child is not None for child in existing_children):
                    self._conflict(group.external_group_key, "child ID already exists")
                if any(child.id in memberships for child in group.children):
                    self._conflict(group.external_group_key, "child membership exists")
                continue
            if any(child is None for child in existing_children):
                self._conflict(group.external_group_key, "existing group is partial")
            self._compare_group(existing_group, group, subject)
            for child, existing_question in zip(group.children, existing_children):
                assert existing_question is not None
                self._compare_question(
                    existing_question,
                    group,
                    child,
                    subject,
                    problem_types,
                    concepts,
                    outcomes,
                )
                membership = memberships.get(child.id)
                if membership is None or membership.group_id != group.id:
                    self._conflict(
                        group.external_group_key, "child membership differs"
                    )

    def _compare_group(
        self,
        existing: QuestionGroup,
        expected: TrustedGroupCandidate,
        subject: Subject,
    ) -> None:
        values = {
            "subject_id": subject.id,
            "content": expected.content,
            "group_type": QuestionGroupType.TRUE_FALSE_FOUR,
            "scoring_policy": QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
            "difficulty": expected.difficulty,
            "source_type": expected.source_lineage["source_code"],
            "source_reference": expected.source_lineage["source_evidence_id"],
            "source_year": None,
            "cognitive_level": None,
            "exam_weight": 1.0,
            "status": QuestionStatus.DRAFT,
        }
        if any(getattr(existing, field) != value for field, value in values.items()):
            self._conflict(expected.external_group_key, "group content drift")
        actual_items = sorted(existing.items, key=lambda item: item.order_index)
        expected_items = list(expected.children)
        if len(actual_items) != 4 or any(
            item.question_id != child.id
            or item.label != child.label
            or item.order_index != child.order_index
            for item, child in zip(actual_items, expected_items)
        ):
            self._conflict(expected.external_group_key, "group membership drift")

    def _compare_question(
        self,
        existing: Question,
        group: TrustedGroupCandidate,
        child: TrustedGroupChildCandidate,
        subject: Subject,
        problem_types: dict[str, ProblemType],
        concepts: dict[str, Concept],
        outcomes: dict[str, LearningOutcome],
    ) -> None:
        values = {
            "subject_id": subject.id,
            "content": child.content,
            "question_type": QuestionType.TRUE_FALSE,
            "difficulty": child.difficulty,
            "correct_answer": child.correct_answer,
            "explanation": None,
            "source_type": group.source_lineage["source_code"],
            "source_reference": group.source_lineage["source_evidence_id"],
            "source_year": None,
            "cognitive_level": None,
            "exam_weight": 0.0,
            "status": QuestionStatus.DRAFT,
        }
        if any(getattr(existing, field) != value for field, value in values.items()):
            self._conflict(child.external_question_key, "question content drift")
        expected_problem_links = {
            (problem_types[link.code].id, link.weight, link.is_primary)
            for link in child.problem_types
        }
        actual_problem_links = {
            (link.problem_type_id, link.weight, link.is_primary)
            for link in existing.problem_type_links
        }
        expected_concept_links = {
            (concepts[link.code].id, link.weight) for link in child.concepts
        }
        actual_concept_links = {
            (link.concept_id, link.weight) for link in existing.concept_links
        }
        expected_outcome_links = {
            (outcomes[link.code].id, link.weight)
            for link in child.learning_outcomes
        }
        actual_outcome_links = {
            (link.learning_outcome_id, link.weight)
            for link in existing.learning_outcome_links
        }
        if (
            actual_problem_links != expected_problem_links
            or actual_concept_links != expected_concept_links
            or actual_outcome_links != expected_outcome_links
        ):
            self._conflict(child.external_question_key, "question taxonomy drift")

    @staticmethod
    def _difficulty_distribution(
        groups: list[TrustedGroupCandidate],
    ) -> dict[str, int]:
        counts = Counter(
            f"{child.difficulty:.2f}"
            for group in groups
            for child in group.children
        )
        return dict(sorted(counts.items()))

    @staticmethod
    def _validate_subject_contract(contract: dict[str, Any]) -> None:
        resolution = contract.get("subject_resolution")
        if not isinstance(resolution, dict) or resolution.get(
            "snapshot_legacy_subject_code"
        ) != LEGACY_SNAPSHOT_SUBJECT_CODE or resolution.get(
            "canonical_subject_code"
        ) != CANONICAL_SUBJECT_CODE:
            raise ApplicationError(
                422,
                "TRUSTED_GROUP_SUBJECT_CONTRACT_INVALID",
                "Trusted importer subject identity contract is invalid.",
            )

    @staticmethod
    def _load_object(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ApplicationError(
                422,
                "PRODUCTION_BRIDGE_DATA_INVALID",
                f"Cannot load {path.name}: {error}.",
            ) from error
        if not isinstance(value, dict):
            raise ApplicationError(
                422,
                "PRODUCTION_BRIDGE_DATA_INVALID",
                f"{path.name} must contain an object.",
            )
        return value

    def _lock(self) -> None:
        assert self.session is not None
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtext("edums:trusted-question-group-import")
                    )
                )
            )

    @staticmethod
    def _conflict(key: str, detail: str) -> None:
        raise ApplicationError(
            409,
            "TRUSTED_GROUP_IMPORT_DRIFT_CONFLICT",
            f"Deterministic import conflict for {key}: {detail}.",
        )
