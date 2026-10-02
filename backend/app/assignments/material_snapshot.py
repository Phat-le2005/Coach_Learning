"""Freeze reviewed teacher material at assignment publish."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.assignments.models import (
    AssignmentMaterialItem,
    AssignmentMaterialItemConcept,
    AssignmentMaterialItemLearningOutcome,
    AssignmentMaterialItemOption,
    AssignmentMaterialItemProblemType,
    AssignmentStatus,
)
from app.core.exceptions import ApplicationError
from app.teacher_materials.models import (
    MaterialItemExtractionStatus,
    MaterialMappingStatus,
    TeacherMaterialItem,
)


def snapshot_material_item(
    session: Session,
    link: AssignmentMaterialItem,
    source: TeacherMaterialItem,
) -> None:
    """Copy the reviewed item once, before its assignment is published."""
    if link.assignment.status != AssignmentStatus.DRAFT:
        raise ApplicationError(
            409, "MATERIAL_SNAPSHOT_IMMUTABLE", "Published snapshots cannot change."
        )
    if source.extraction_status != MaterialItemExtractionStatus.READY:
        raise ApplicationError(
            422, "MATERIAL_ITEM_NOT_READY", "Material item must be READY at publish."
        )
    if not source.raw_metadata.get("content_reviewed"):
        raise ApplicationError(
            422, "ITEM_CONTENT_NOT_REVIEWED", "Material item content must be reviewed."
        )

    concepts = [
        mapping for mapping in source.concept_mappings
        if mapping.status == MaterialMappingStatus.CONFIRMED
    ]
    problem_types = [
        mapping for mapping in source.problem_type_mappings
        if mapping.status == MaterialMappingStatus.CONFIRMED
    ]
    outcomes = [
        mapping for mapping in source.learning_outcome_mappings
        if mapping.status == MaterialMappingStatus.CONFIRMED
    ]
    if not concepts or not problem_types:
        raise ApplicationError(
            422, "MATERIAL_ITEM_MAPPING_REQUIRED",
            "Confirmed Concept and ProblemType mappings are required.",
        )
    if sum(mapping.is_primary for mapping in problem_types) > 1:
        raise ApplicationError(
            422, "MULTIPLE_PRIMARY_PROBLEM_TYPES",
            "At most one primary ProblemType is allowed.",
        )

    link.teacher_material_id = source.teacher_material_id
    link.source_content_hash = source.content_hash
    link.content = source.content
    link.question_type = source.question_type
    link.correct_answer = source.correct_answer
    link.explanation = source.explanation
    link.difficulty = source.difficulty
    link.evaluation_mode = source.evaluation_mode
    link.snapshotted_at = datetime.now(timezone.utc)

    # Keep the draft copy unique if a publish transaction is retried.
    link.options.clear()
    link.concept_mappings.clear()
    link.problem_type_mappings.clear()
    link.learning_outcome_mappings.clear()
    session.flush()
    link.options = [
        AssignmentMaterialItemOption(
            label=option.label,
            content=option.content,
            order_index=option.order_index,
        )
        for option in source.options
    ]
    link.concept_mappings = [
        AssignmentMaterialItemConcept(
            concept_id=mapping.concept_id,
            weight=mapping.weight,
            confidence=mapping.confidence,
            is_primary=mapping.is_primary,
        )
        for mapping in concepts
    ]
    link.problem_type_mappings = [
        AssignmentMaterialItemProblemType(
            problem_type_id=mapping.problem_type_id,
            weight=mapping.weight,
            confidence=mapping.confidence,
            is_primary=mapping.is_primary,
        )
        for mapping in problem_types
    ]
    link.learning_outcome_mappings = [
        AssignmentMaterialItemLearningOutcome(
            learning_outcome_id=mapping.learning_outcome_id,
            weight=mapping.weight,
            confidence=mapping.confidence,
            is_primary=mapping.is_primary,
        )
        for mapping in outcomes
    ]
    session.flush()
