from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.derivative_activation import (
    DATASET_CODE,
    DATASET_VERSION,
    DerivativeTaxonomyActivationValidator,
)
from app.curriculum.import_service import CurriculumImportService
from app.curriculum.models import (
    CurriculumImportHistory,
    ProblemType,
    ProblemTypeConcept,
    ProblemTypeLearningOutcome,
)
from app.questions.group_import_service import TrustedQuestionGroupImportService
from app.questions.models import Question, QuestionGroup
from app.users.models import Role, User
from tests.questions.test_group_import_service import _seed_candidate_entities_only


EXPECTED_COUNTS = {
    "subjects": 1,
    "chapters": 6,
    "topics": 10,
    "problem_types": 30,
    "concepts": 41,
    "learning_outcomes": 18,
    "concept_relations": 48,
    "problem_type_concepts": 100,
    "problem_type_learning_outcomes": 40,
}


def _import_candidate(session: Session, tmp_path: Path):
    data_root = tmp_path / "curriculum"
    expected = DerivativeTaxonomyActivationValidator.write_import_dataset(data_root)
    result = CurriculumImportService(session, data_root=data_root).import_dataset(
        DATASET_CODE
    )
    return expected, result


def _actor(
    question_user_factory: Callable[[Role, str], User], suffix: str
) -> User:
    return question_user_factory(Role.ADMIN, f"activation-{suffix}@example.com")


def _assert_confirm_blocked(
    session: Session,
    actor: User,
) -> None:
    service = TrustedQuestionGroupImportService(session)
    with pytest.raises(ApplicationError) as captured:
        service.confirm(service.preview(), actor.id)
    assert captured.value.status_code == 409
    assert captured.value.code == "TRUSTED_GROUP_TAXONOMY_NOT_ACTIVATED"
    assert session.scalar(select(func.count()).select_from(Question)) == 0
    assert session.scalar(select(func.count()).select_from(QuestionGroup)) == 0


def test_real_curriculum_import_activates_exact_graph(
    db_session: Session,
    tmp_path: Path,
) -> None:
    expected, imported = _import_candidate(db_session, tmp_path)

    history = db_session.scalar(
        select(CurriculumImportHistory).where(
            CurriculumImportHistory.dataset_code == DATASET_CODE,
            CurriculumImportHistory.dataset_version == DATASET_VERSION,
        )
    )
    report = DerivativeTaxonomyActivationValidator(db_session).validate()

    assert imported.created["curriculum_import_history"] == 1
    assert history is not None
    assert history.content_hash == expected.content_hash
    assert report.is_valid, report.as_dict()
    assert report.history_status == "MATCHED"
    assert report.candidate_counts == EXPECTED_COUNTS
    assert report.database_counts == EXPECTED_COUNTS
    assert report.candidate_fingerprint == report.database_fingerprint
    assert report.expected_import_content_hash == expected.content_hash


def test_manual_entity_only_seed_cannot_confirm(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
) -> None:
    _seed_candidate_entities_only(db_session)
    actor = _actor(question_user_factory, "entities-only")

    report = DerivativeTaxonomyActivationValidator(db_session).validate()
    assert not report.is_valid
    assert report.database_counts["concept_relations"] == 0
    assert report.database_counts["problem_type_concepts"] == 0
    assert report.database_counts["problem_type_learning_outcomes"] == 0
    assert report.history_status == "MISSING"
    _assert_confirm_blocked(db_session, actor)


def _mutate_missing_relation(session: Session) -> None:
    row = session.scalar(select(ConceptRelation).limit(1))
    assert row is not None
    session.delete(row)


def _mutate_relation_endpoint(session: Session) -> None:
    row = session.scalar(
        select(ConceptRelation)
        .where(ConceptRelation.relation_type == RelationType.PREREQUISITE)
        .limit(1)
    )
    assert row is not None
    existing = set(session.execute(
        select(
            ConceptRelation.source_concept_id,
            ConceptRelation.target_concept_id,
            ConceptRelation.relation_type,
        )
    ))
    concepts = list(session.scalars(select(Concept)))
    target = next(
        concept for concept in concepts
        if concept.id != row.source_concept_id
        and (row.source_concept_id, concept.id, row.relation_type) not in existing
    )
    row.target_concept_id = target.id


def _mutate_missing_problem_concept(session: Session) -> None:
    row = session.scalar(select(ProblemTypeConcept).limit(1))
    assert row is not None
    session.delete(row)


def _mutate_problem_concept_weight(session: Session) -> None:
    row = session.scalar(select(ProblemTypeConcept).limit(1))
    assert row is not None
    row.weight = 0.123


def _mutate_problem_concept_primary(session: Session) -> None:
    row = session.scalar(select(ProblemTypeConcept).limit(1))
    assert row is not None
    row.is_primary = not row.is_primary


def _mutate_missing_problem_outcome(session: Session) -> None:
    row = session.scalar(select(ProblemTypeLearningOutcome).limit(1))
    assert row is not None
    session.delete(row)


def _mutate_problem_outcome_weight(session: Session) -> None:
    row = session.scalar(select(ProblemTypeLearningOutcome).limit(1))
    assert row is not None
    row.weight = 0.123 if row.weight != 0.123 else 0.124


def _mutate_history_missing(session: Session) -> None:
    row = session.scalar(select(CurriculumImportHistory))
    assert row is not None
    session.delete(row)


def _mutate_history_version(session: Session) -> None:
    row = session.scalar(select(CurriculumImportHistory))
    assert row is not None
    row.dataset_version = "1.2.1"


def _mutate_history_hash(session: Session) -> None:
    row = session.scalar(select(CurriculumImportHistory))
    assert row is not None
    row.content_hash = "0" * 64


def _mutate_stable_identity(session: Session) -> None:
    row = session.scalar(select(ConceptRelation).limit(1))
    assert row is not None
    row.id = uuid4()


def _mutate_entity_field(session: Session) -> None:
    row = session.scalar(select(ProblemType).limit(1))
    assert row is not None
    row.default_difficulty = (
        0.01 if row.default_difficulty is None else round(row.default_difficulty + 0.01, 2)
    )


@pytest.mark.parametrize(
    ("case", "mutation", "expected_issue"),
    [
        ("relation-missing", _mutate_missing_relation, "TAXONOMY_COUNTS_MISMATCH"),
        ("relation-endpoint", _mutate_relation_endpoint, "TAXONOMY_FINGERPRINT_MISMATCH"),
        ("problem-concept-missing", _mutate_missing_problem_concept, "TAXONOMY_COUNTS_MISMATCH"),
        ("problem-concept-weight", _mutate_problem_concept_weight, "TAXONOMY_FINGERPRINT_MISMATCH"),
        ("problem-concept-primary", _mutate_problem_concept_primary, "TAXONOMY_FINGERPRINT_MISMATCH"),
        ("problem-outcome-missing", _mutate_missing_problem_outcome, "TAXONOMY_COUNTS_MISMATCH"),
        ("problem-outcome-weight", _mutate_problem_outcome_weight, "TAXONOMY_FINGERPRINT_MISMATCH"),
        ("history-missing", _mutate_history_missing, "IMPORT_HISTORY_MISSING"),
        ("history-version", _mutate_history_version, "IMPORT_HISTORY_VERSION_MISMATCH"),
        ("history-hash", _mutate_history_hash, "IMPORT_HISTORY_HASH_MISMATCH"),
        ("stable-identity", _mutate_stable_identity, "STABLE_ID_MISMATCH"),
        ("entity-field", _mutate_entity_field, "TAXONOMY_FINGERPRINT_MISMATCH"),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_confirm_rejects_each_activation_drift_before_writes(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
    tmp_path: Path,
    case: str,
    mutation: Callable[[Session], None],
    expected_issue: str,
) -> None:
    _import_candidate(db_session, tmp_path)
    actor = _actor(question_user_factory, case)
    mutation(db_session)
    db_session.commit()

    report = DerivativeTaxonomyActivationValidator(db_session).validate()
    assert not report.is_valid
    assert expected_issue in {issue.code for issue in report.errors}
    _assert_confirm_blocked(db_session, actor)
