"""Add the complete development tree without replacing existing PA2 identities."""
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.curriculum.development_tree import DEVELOPMENT_TREE_DATASET, DEVELOPMENT_TREE_ROOT
from app.curriculum.import_service import CurriculumImportService
from app.curriculum.models import Chapter, CurriculumVersion, LearningOutcome, ProblemType, ProblemTypeConcept, ProblemTypeLearningOutcome, Topic
from app.subjects.models import Subject


def ensure_ocr_pa2_tree(session: Session, *, app_env: str) -> dict:
    """Caller owns the transaction. Keep UUIDs, question links and legacy nodes."""
    if app_env == "production":
        raise ValueError("This tree installer is restricted to development/test.")
    importer = CurriculumImportService(session, data_root=DEVELOPMENT_TREE_ROOT.parent)
    dataset = importer._load(DEVELOPMENT_TREE_DATASET)
    importer._lock()
    subject = session.scalar(select(Subject).where(Subject.code == dataset.subject.code).with_for_update())
    if subject is None:
        raise ValueError("Install the base subject before the PA2 milestone.")
    version = session.get(CurriculumVersion, subject.curriculum_version_id)
    if version.code != dataset.manifest.curriculum_version_code:
        raise ValueError("PA2 tree must use the existing subject curriculum version.")
    created = Counter()
    moved = []

    def index(rows):
        result = {}
        for row in rows:
            if row.code in result:
                raise ValueError(f"Ambiguous existing curriculum code: {row.code}")
            result[row.code] = row
        return result

    def add(model, rows, code, values):
        if code not in rows:
            row = model(**values)
            session.add(row)
            session.flush()
            rows[code] = row
            created[model.__tablename__] += 1
        return rows[code]

    chapters = index(session.scalars(select(Chapter).where(Chapter.subject_id == subject.id)))
    topics = index(session.scalars(select(Topic).join(Chapter).where(Chapter.subject_id == subject.id)))
    problems = index(session.scalars(select(ProblemType).join(Topic).join(Chapter).where(Chapter.subject_id == subject.id)))
    concepts = index(session.scalars(select(Concept).where(Concept.subject_id == subject.id)))
    outcomes = index(session.scalars(select(LearningOutcome).where(LearningOutcome.subject_id == subject.id)))
    for spec in dataset.chapters:
        add(Chapter, chapters, spec.code, {"subject_id": subject.id, **spec.model_dump()})
    for spec in dataset.topics:
        row = add(Topic, topics, spec.code, {"chapter_id": chapters[spec.chapter_code].id,
                                          **spec.model_dump(exclude={"chapter_code"})})
        if row.chapter_id != chapters[spec.chapter_code].id:
            moved.append(spec.code)
    for spec in dataset.concepts:
        add(Concept, concepts, spec.code, {"subject_id": subject.id, **spec.model_dump()})
    for spec in dataset.learning_outcomes:
        add(LearningOutcome, outcomes, spec.code, {"subject_id": subject.id, **spec.model_dump()})
    for spec in dataset.problem_types:
        row = add(ProblemType, problems, spec.code, {"topic_id": topics[spec.topic_code].id,
                                                   **spec.model_dump(exclude={"topic_code"})})
        if row.topic_id != topics[spec.topic_code].id:
            moved.append(spec.code)
        row.is_active = True
    for spec in dataset.problem_type_concepts:
        key = (problems[spec.problem_type_code].id, concepts[spec.concept_code].id)
        if session.get(ProblemTypeConcept, key) is None:
            session.add(ProblemTypeConcept(problem_type_id=key[0], concept_id=key[1],
                                          weight=spec.weight, is_primary=spec.is_primary))
            created["problem_type_concepts"] += 1
    for spec in dataset.problem_type_outcomes:
        key = (problems[spec.problem_type_code].id, outcomes[spec.learning_outcome_code].id)
        if session.get(ProblemTypeLearningOutcome, key) is None:
            session.add(ProblemTypeLearningOutcome(problem_type_id=key[0], learning_outcome_id=key[1], weight=spec.weight))
            created["problem_type_learning_outcomes"] += 1
    edges = {(r.source_concept_id, r.target_concept_id, r.relation_type) for r in session.scalars(
        select(ConceptRelation).where(ConceptRelation.source_concept_id.in_([c.id for c in concepts.values()]))) }
    # Use the same graph validator as the importer, including existing prerequisites.
    ids = {c.id: c.code for c in concepts.values()}
    from app.curriculum.import_schemas import ConceptRelationRecord
    combined = [ConceptRelationRecord(source_code=ids[a], target_code=ids[b], relation_type=kind)
                for a, b, kind in edges if a in ids and b in ids]
    for spec in dataset.concept_relations:
        a, b, kind = concepts[spec.source_code].id, concepts[spec.target_code].id, spec.relation_type
        if kind == RelationType.RELATED_TO and a > b:
            a, b = b, a
        if (a, b, kind) not in edges:
            combined.append(spec)
            edges.add((a, b, kind))
            session.add(ConceptRelation(source_concept_id=a, target_concept_id=b, relation_type=kind))
            created["concept_relations"] += 1
    importer._validate_graph(combined, set(concepts))
    session.flush()
    return {"dataset": DEVELOPMENT_TREE_DATASET, "created": dict(created),
            "target_counts": dataset.counts, "preserved_parent_placements": sorted(moved),
            "total_chapters_including_legacy": len(chapters), "total_problem_types_including_legacy": len(problems),
            "total_concepts_including_pa2": len(concepts), "question_ids_unchanged": True}
