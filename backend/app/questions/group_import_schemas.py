from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GroupImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GroupImportProblemTypeLink(GroupImportModel):
    code: str
    weight: float = Field(gt=0.0, le=1.0)
    is_primary: bool


class GroupImportConceptLink(GroupImportModel):
    code: str
    weight: float = Field(gt=0.0, le=1.0)


class GroupImportOutcomeLink(GroupImportModel):
    code: str
    weight: float | None = Field(default=None, gt=0.0, le=1.0)


class TrustedGroupChildCandidate(GroupImportModel):
    id: UUID
    external_question_key: str
    label: str
    order_index: int
    question_type: str
    content: str
    correct_answer: str
    difficulty: float = Field(ge=0.0, le=1.0)
    exam_weight: float = Field(ge=0.0, le=1.0)
    cognitive_level: None = None
    explanation: None = None
    problem_types: tuple[GroupImportProblemTypeLink, ...]
    concepts: tuple[GroupImportConceptLink, ...]
    learning_outcomes: tuple[GroupImportOutcomeLink, ...]
    taxonomy_basis: str


class TrustedGroupCandidate(GroupImportModel):
    id: UUID
    external_group_key: str
    subject_code: str
    snapshot_subject_code: str
    group_type: str
    scoring_policy: str
    content: str
    difficulty: float = Field(ge=0.0, le=1.0)
    exam_weight: float = Field(ge=0.0, le=1.0)
    cognitive_level: None = None
    status: str
    visual_asset_id: str | None
    source_lineage: dict[str, Any]
    review_lineage: dict[str, Any]
    rights_status: str
    children: tuple[TrustedGroupChildCandidate, ...]
    production_release_eligible: bool


class TrustedGroupImportPreview(GroupImportModel):
    dataset_code: str
    target_subject_code: str
    snapshot_subject_code: str
    curriculum_candidate_version: str
    curriculum_candidate_hash: str
    promotion_snapshot_hash: str
    raw_candidate_sha256: str
    groups: tuple[TrustedGroupCandidate, ...]
    counts: dict[str, int]
    child_difficulty_distribution: dict[str, int]
    rights_statuses: tuple[str, ...]
    production_release_eligible: int
    database_import_ready: bool


class TrustedGroupImportResult(GroupImportModel):
    preview: TrustedGroupImportPreview
    created: dict[str, int]
    unchanged: dict[str, int]
    source_lineage: tuple[dict[str, Any], ...]
