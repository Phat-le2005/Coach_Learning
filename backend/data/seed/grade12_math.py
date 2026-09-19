"""Deprecated compatibility view over the canonical JSON curriculum dataset.

New code must use ``CurriculumImportService``. These exports are derived from
the JSON files so this module cannot become a second source of curriculum facts.
"""

import json
from pathlib import Path

from data.seed.records import ConceptSeed, SubjectSeed

_DATASET = Path(__file__).resolve().parents[1] / "curriculum" / "math" / "grade12" / "gdpt2018"
_subject = json.loads((_DATASET / "subject.json").read_text(encoding="utf-8"))
_concepts = json.loads((_DATASET / "concepts.json").read_text(encoding="utf-8"))
_relations = json.loads((_DATASET / "concept_relations.json").read_text(encoding="utf-8"))

SUBJECT = SubjectSeed(
    code=_subject["code"],
    name=_subject["name"],
    grade_level=_subject["grade_level"],
    description=_subject["description"],
)
CONCEPTS = tuple(
    ConceptSeed(
        item["code"],
        item["name"],
        item["description"],
        item["grade_level"],
        item["order_index"],
    )
    for item in _concepts
)
PREREQUISITES = tuple(
    (item["source_code"], item["target_code"])
    for item in _relations
    if item["relation_type"] == "PREREQUISITE"
)
