"""Small additive catalog bridge for the original development curriculum.

Adds the concepts used by the reviewed cubic profile to an existing subject.
It never activates a different tree, edits a mapping or replaces existing rows.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.concepts.schemas import ConceptCreate
from app.curriculum.models import CurriculumVersion, LearningOutcome
from app.curriculum.schemas import LearningOutcomeCreate
from app.subjects.models import Subject


CONCEPTS = {
    "FUNCTION_DOMAIN": ("Tập xác định của hàm số", "FUNCTION"),
    "DERIVATIVE_RULES": ("Quy tắc tính đạo hàm", "DERIVATIVE"),
    "SIGN_ANALYSIS": ("Xét dấu biểu thức", "INEQUALITY_SOLVING"),
    "MONOTONICITY_CRITERION": ("Dấu đạo hàm và tính đơn điệu", "MONOTONICITY"),
}
OUTCOMES = {
    "M12_DERIV_LO_01": "Nhận biết và xét tính đồng biến, nghịch biến của hàm số bằng đạo hàm.",
    "M12_DERIV_LO_02": "Sử dụng bảng biến thiên để xác định các khoảng đơn điệu của hàm số.",
}


def add_missing_cubic_catalog(session: Session, *, subject_code: str, version_code: str) -> dict:
    """Caller owns the transaction. Safe to repeat; no existing row is updated."""
    subjects = list(session.scalars(select(Subject).join(CurriculumVersion).where(
        Subject.code == subject_code, CurriculumVersion.code == version_code).with_for_update()))
    if len(subjects) != 1:
        raise ValueError("Catalog additions require exactly one existing subject/version")
    subject = subjects[0]
    existing = {c.code: c for c in session.scalars(select(Concept).where(Concept.subject_id == subject.id))}
    created, edges, outcomes = [], [], []
    for code, (name, parent) in CONCEPTS.items():
        if code in existing:
            continue
        data = ConceptCreate(subject_id=subject.id, code=code, name=name, grade_level=12,
                             description="Kỹ năng chi tiết cho rubric dữ liệu OCR đã kiểm tra.")
        concept = Concept(**data.model_dump())
        session.add(concept); session.flush()
        existing[code] = concept
        created.append(code)
        if parent in existing:
            session.add(ConceptRelation(source_concept_id=concept.id, target_concept_id=existing[parent].id,
                                        relation_type=RelationType.PART_OF))
            edges.append(f"{code}:PART_OF:{parent}")
    for code, description in OUTCOMES.items():
        if session.scalar(select(LearningOutcome.id).where(LearningOutcome.subject_id == subject.id, LearningOutcome.code == code)):
            continue
        data = LearningOutcomeCreate(subject_id=subject.id, code=code, description=description, grade_level=12,
                                     source_reference="Existing repository Math 12 curriculum codes; OCR cubic profile")
        session.add(LearningOutcome(**data.model_dump()))
        outcomes.append(code)
    source, target = existing["SIGN_ANALYSIS"], existing["MONOTONICITY_CRITERION"]
    if not session.scalar(select(ConceptRelation.id).where(
            ConceptRelation.source_concept_id == source.id, ConceptRelation.target_concept_id == target.id,
            ConceptRelation.relation_type == RelationType.PREREQUISITE)):
        session.add(ConceptRelation(source_concept_id=source.id, target_concept_id=target.id,
                                    relation_type=RelationType.PREREQUISITE))
        edges.append("SIGN_ANALYSIS:PREREQUISITE:MONOTONICITY_CRITERION")
    session.flush()
    return {"subject_id": str(subject.id), "created_concepts": created,
            "created_outcomes": outcomes, "created_relations": edges}


def add_missing_probability_catalog(session: Session, *, subject_code: str, version_code: str) -> dict:
    from app.curriculum.models import Chapter, Topic, ProblemType, ProblemTypeConcept, ProblemTypeLearningOutcome
    subjects = list(session.scalars(select(Subject).join(CurriculumVersion).where(
        Subject.code == subject_code, CurriculumVersion.code == version_code).with_for_update()))
    if len(subjects) != 1:
        raise ValueError("Probability additions require one existing subject/version")
    subject = subjects[0]
    names = {"PROBABILITY_DATA": "Đọc và xác định dữ kiện xác suất",
             "PROBABILITY_ARITHMETIC": "Tính các xác suất trung gian",
             "CONDITIONAL_PROBABILITY": "Xác suất có điều kiện",
             "TOTAL_PROBABILITY": "Công thức xác suất toàn phần", "BAYES_FORMULA": "Công thức Bayes"}
    concepts = {c.code: c for c in session.scalars(select(Concept).where(Concept.subject_id == subject.id))}
    created = []
    for code, name in names.items():
        if code not in concepts:
            data = ConceptCreate(subject_id=subject.id, code=code, name=name, grade_level=12)
            concepts[code] = Concept(**data.model_dump()); session.add(concepts[code]); session.flush()
            created.append(code)
    new_relations = []
    if "PROBABILITY" in concepts:
        for code in created:
            session.add(ConceptRelation(source_concept_id=concepts[code].id, target_concept_id=concepts["PROBABILITY"].id,
                                        relation_type=RelationType.PART_OF))
            new_relations.append(code + ":PART_OF:PROBABILITY")
    outcome_codes = {"LO_M12_CONDITIONAL_PROBABILITY": "Tính và vận dụng xác suất có điều kiện.",
                     "LO_M12_TOTAL_PROBABILITY": "Vận dụng công thức xác suất toàn phần.",
                     "LO_M12_BAYES": "Vận dụng công thức Bayes để tính xác suất hậu nghiệm."}
    added_outcomes = []
    for code, description in outcome_codes.items():
        if not session.scalar(select(LearningOutcome.id).where(LearningOutcome.subject_id == subject.id, LearningOutcome.code == code)):
            data = LearningOutcomeCreate(subject_id=subject.id, code=code, description=description, grade_level=12)
            session.add(LearningOutcome(**data.model_dump())); added_outcomes.append(code)
    pts = {p.code: p for p in session.scalars(select(ProblemType).join(Topic).join(Chapter).where(Chapter.subject_id == subject.id))}
    specs = {"CONDITIONAL_PROBABILITY_DIRECT": ("Tính xác suất có điều kiện", .4, "CONDITIONAL_PROBABILITY"),
             "TOTAL_PROBABILITY": ("Vận dụng xác suất toàn phần", .55, "TOTAL_PROBABILITY"),
             "BAYES_POSTERIOR": ("Vận dụng công thức Bayes", .6, "BAYES_FORMULA")}
    added_pts = []
    session.flush()
    outcomes = {o.code: o for o in session.scalars(select(LearningOutcome).where(LearningOutcome.subject_id == subject.id))}
    for code, (name, difficulty, skill) in specs.items():
        if code in pts:
            continue
        base = pts.get("BASIC_PROBABILITY")
        if base is None:
            raise ValueError("A probability topic must already exist before adding these problem types")
        pt = ProblemType(topic_id=base.topic_id, code=code, name=name, order_index=base.order_index + 10 + len(added_pts),
                         default_difficulty=difficulty, is_active=True)
        session.add(pt); session.flush()
        for concept_code, weight in (("PROBABILITY_DATA", .2), ("PROBABILITY_ARITHMETIC", .3), (skill, .5)):
            session.add(ProblemTypeConcept(problem_type_id=pt.id, concept_id=concepts[concept_code].id,
                                          weight=weight, is_primary=concept_code == skill))
        outcome_code = {"CONDITIONAL_PROBABILITY_DIRECT": "LO_M12_CONDITIONAL_PROBABILITY",
                        "TOTAL_PROBABILITY": "LO_M12_TOTAL_PROBABILITY", "BAYES_POSTERIOR": "LO_M12_BAYES"}[code]
        session.add(ProblemTypeLearningOutcome(problem_type_id=pt.id, learning_outcome_id=outcomes[outcome_code].id, weight=1.0))
        added_pts.append(code)
    session.flush()
    return {"subject_id": str(subject.id), "created_concepts": created, "created_outcomes": added_outcomes,
            "created_problem_types": added_pts, "created_relations": new_relations}


def add_missing_reviewed_catalog(session: Session, *, subject_code: str, version_code: str, family: str) -> dict:
    """Add only the existing repository taxonomy needed by a selected capability."""
    import json
    from pathlib import Path
    from app.curriculum.models import Chapter, Topic, ProblemType, ProblemTypeConcept, ProblemTypeLearningOutcome
    from app.curriculum.import_schemas import ChapterRecord, TopicRecord, ProblemTypeRecord, ConceptRecord, LearningOutcomeRecord
    from app.math_solutions.numeric_reference import STATS_CONCEPTS, INTEGRAL_CONCEPTS, EXTREMA_CONCEPTS
    root = Path(__file__).resolve().parents[2] / "data/fixtures/curriculum/math_g12_full_tree_v0_1"
    read = lambda name: json.loads((root / (name + ".json")).read_text(encoding="utf-8"))
    subjects = list(session.scalars(select(Subject).join(CurriculumVersion).where(
        Subject.code == subject_code, CurriculumVersion.code == version_code).with_for_update()))
    if len(subjects) != 1:
        raise ValueError("Catalog additions require one existing subject/version")
    subject = subjects[0]
    if family == "grouped_statistics":
        pt_codes = {"CALCULATE_GROUPED_RANGE", "CALCULATE_GROUPED_IQR", "CALCULATE_GROUPED_VARIANCE", "CALCULATE_GROUPED_STANDARD_DEVIATION"}
        concept_codes = set(STATS_CONCEPTS)
    elif family == "definite_integral":
        pt_codes = {"CALCULATE_DEFINITE_INTEGRAL", "INTEGRAL_PROPERTIES", "AREA_BY_INTEGRAL", "VOLUME_BY_INTEGRAL", "VOLUME_BY_CROSS_SECTION"}
        concept_codes = set(INTEGRAL_CONCEPTS)
    elif family == "polynomial_extrema":
        pt_codes = {"FIND_FUNCTION_EXTREMA"}
        concept_codes = set(EXTREMA_CONCEPTS)
    else:
        raise ValueError("Unsupported additive taxonomy family")
    pt_specs = [ProblemTypeRecord.model_validate(row) for row in read("problem_types") if row["code"] in pt_codes]
    topic_codes = {row.topic_code for row in pt_specs}
    topic_specs = [TopicRecord.model_validate(row) for row in read("topics") if row["code"] in topic_codes]
    chapter_codes = {row.chapter_code for row in topic_specs}
    concept_links = [row for row in read("problem_type_concepts") if row["problem_type_code"] in pt_codes]
    concept_codes.update(row["concept_code"] for row in concept_links)
    outcome_links = [row for row in read("problem_type_learning_outcomes") if row["problem_type_code"] in pt_codes]
    outcome_codes = {row["learning_outcome_code"] for row in outcome_links}
    report = {"family": family, "created_chapters": [], "created_topics": [], "created_problem_types": [],
              "created_concepts": [], "created_outcomes": [], "created_relations": []}
    chapters = {row.code: row for row in session.scalars(select(Chapter).where(Chapter.subject_id == subject.id))}
    for spec in [ChapterRecord.model_validate(row) for row in read("chapters") if row["code"] in chapter_codes]:
        if spec.code not in chapters:
            row = Chapter(subject_id=subject.id, **spec.model_dump()); session.add(row); session.flush()
            chapters[spec.code] = row; report["created_chapters"].append(spec.code)
    topics = {row.code: row for row in session.scalars(select(Topic).join(Chapter).where(Chapter.subject_id == subject.id))}
    for spec in topic_specs:
        if spec.code not in topics:
            row = Topic(chapter_id=chapters[spec.chapter_code].id, **spec.model_dump(exclude={"chapter_code"})); session.add(row); session.flush()
            topics[spec.code] = row; report["created_topics"].append(spec.code)
    concepts = {row.code: row for row in session.scalars(select(Concept).where(Concept.subject_id == subject.id))}
    for spec in [ConceptRecord.model_validate(row) for row in read("concepts") if row["code"] in concept_codes]:
        if spec.code not in concepts:
            row = Concept(subject_id=subject.id, **spec.model_dump()); session.add(row); session.flush()
            concepts[spec.code] = row; report["created_concepts"].append(spec.code)
    outcomes = {row.code: row for row in session.scalars(select(LearningOutcome).where(LearningOutcome.subject_id == subject.id))}
    for spec in [LearningOutcomeRecord.model_validate(row) for row in read("learning_outcomes") if row["code"] in outcome_codes]:
        if spec.code not in outcomes:
            row = LearningOutcome(subject_id=subject.id, **spec.model_dump()); session.add(row); session.flush()
            outcomes[spec.code] = row; report["created_outcomes"].append(spec.code)
    pts = {row.code: row for row in session.scalars(select(ProblemType).join(Topic).join(Chapter).where(Chapter.subject_id == subject.id))}
    for spec in pt_specs:
        if spec.code not in pts:
            row = ProblemType(topic_id=topics[spec.topic_code].id, **spec.model_dump(exclude={"topic_code"})); session.add(row); session.flush()
            pts[spec.code] = row; report["created_problem_types"].append(spec.code)
            for link in [link for link in concept_links if link["problem_type_code"] == spec.code]:
                session.add(ProblemTypeConcept(problem_type_id=row.id, concept_id=concepts[link["concept_code"]].id,
                                              weight=link["weight"], is_primary=link["is_primary"]))
            for link in [link for link in outcome_links if link["problem_type_code"] == spec.code]:
                session.add(ProblemTypeLearningOutcome(problem_type_id=row.id, learning_outcome_id=outcomes[link["learning_outcome_code"]].id, weight=link["weight"]))
    # Add edges only involving newly created concepts, preserving existing graph semantics.
    for edge in read("concept_relations"):
        if (edge["source_code"] in concepts and edge["target_code"] in concepts
                and {edge["source_code"], edge["target_code"]} & set(report["created_concepts"])):
            source, target = concepts[edge["source_code"]], concepts[edge["target_code"]]
            kind = RelationType(edge["relation_type"])
            if kind == RelationType.RELATED_TO and source.id > target.id: source, target = target, source
            session.add(ConceptRelation(source_concept_id=source.id, target_concept_id=target.id, relation_type=kind))
            report["created_relations"].append(f"{edge['source_code']}:{kind.value}:{edge['target_code']}")
    session.flush()
    return report
