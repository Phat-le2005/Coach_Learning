from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.curriculum.models import ProblemType
from app.misconceptions.models import MisconceptionDefinition
from app.questions.models import Question, QuestionConcept, QuestionProblemType


@dataclass(frozen=True, slots=True)
class ScopedTaxonomy:
    """Taxonomy definitions and allowed identifiers scoped strictly to a question."""

    definitions: list[MisconceptionDefinition]
    allowed_codes: set[str]
    allowed_concept_ids: set[UUID]
    allowed_problem_type_ids: set[UUID]
    allowed_prerequisite_concept_ids: set[UUID]
    concepts_by_id: dict[UUID, Concept]
    problem_types_by_id: dict[UUID, ProblemType]

    def format_for_prompt(self) -> str:
        """Render a readable textual whitelist of misconception definitions for LLM context."""
        if not self.definitions:
            return "(No active misconception definitions found in scope. Output 'UNKNOWN'.)"

        lines: list[str] = []
        for d in self.definitions:
            concept = self.concepts_by_id.get(d.concept_id)
            concept_str = f"{concept.name} ({concept.code})" if concept else str(d.concept_id)
            prereq_tag = " [PREREQUISITE]" if d.concept_id in self.allowed_prerequisite_concept_ids else ""

            pt_str = "Any"
            if d.problem_type_id:
                pt = self.problem_types_by_id.get(d.problem_type_id)
                pt_str = f"{pt.name} ({pt.code})" if pt else str(d.problem_type_id)

            lines.append(
                f"- Code: {d.code}\n"
                f"  Concept: {concept_str}{prereq_tag} (id: {d.concept_id})\n"
                f"  Problem Type: {pt_str} (id: {d.problem_type_id or 'None'})\n"
                f"  Category: {d.category.value}\n"
                f"  Name: {d.name}\n"
                f"  Description: {d.description}"
            )
        return "\n\n".join(lines)


class TaxonomyScoper:
    """Scopes active misconception definitions strictly to question concepts, problem types,
    and prerequisite concepts."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_scoped_taxonomy(self, question: Question) -> ScopedTaxonomy:
        # 1. Direct question concepts
        direct_concept_ids: list[UUID] = list(
            self.session.scalars(
                select(QuestionConcept.concept_id).where(
                    QuestionConcept.question_id == question.id
                )
            ).all()
        )

        # 2. Direct question problem types
        direct_problem_type_ids: list[UUID] = list(
            self.session.scalars(
                select(QuestionProblemType.problem_type_id).where(
                    QuestionProblemType.question_id == question.id
                )
            ).all()
        )

        # 3. Prerequisite concepts via ConceptRelation (target is question concept, source is prerequisite)
        prerequisite_concept_ids: list[UUID] = []
        if direct_concept_ids:
            prerequisite_concept_ids = list(
                self.session.scalars(
                    select(ConceptRelation.source_concept_id).where(
                        ConceptRelation.target_concept_id.in_(direct_concept_ids),
                        ConceptRelation.relation_type == RelationType.PREREQUISITE,
                    )
                ).all()
            )

        all_concept_ids = set(direct_concept_ids) | set(prerequisite_concept_ids)
        all_problem_type_ids = set(direct_problem_type_ids)
        prereq_concept_ids_set = set(prerequisite_concept_ids)

        # 4. Fetch active definitions matching scoped concepts or problem types
        definitions: list[MisconceptionDefinition] = []
        if all_concept_ids or all_problem_type_ids:
            conditions = []
            if all_concept_ids:
                conditions.append(MisconceptionDefinition.concept_id.in_(all_concept_ids))
            if all_problem_type_ids:
                conditions.append(MisconceptionDefinition.problem_type_id.in_(all_problem_type_ids))

            query = (
                select(MisconceptionDefinition)
                .where(
                    MisconceptionDefinition.is_active.is_(True),
                    or_(*conditions),
                )
                .order_by(MisconceptionDefinition.code)
            )
            definitions = list(self.session.scalars(query).all())

        # 5. Preload concept and problem type names for clean prompt formatting
        concepts_by_id: dict[UUID, Concept] = {}
        if all_concept_ids:
            concepts = self.session.scalars(
                select(Concept).where(Concept.id.in_(all_concept_ids))
            ).all()
            concepts_by_id = {c.id: c for c in concepts}

        problem_types_by_id: dict[UUID, ProblemType] = {}
        if all_problem_type_ids:
            pts = self.session.scalars(
                select(ProblemType).where(ProblemType.id.in_(all_problem_type_ids))
            ).all()
            problem_types_by_id = {pt.id: pt for pt in pts}

        allowed_codes = {d.code for d in definitions}

        return ScopedTaxonomy(
            definitions=definitions,
            allowed_codes=allowed_codes,
            allowed_concept_ids=all_concept_ids,
            allowed_problem_type_ids=all_problem_type_ids,
            allowed_prerequisite_concept_ids=prereq_concept_ids_set,
            concepts_by_id=concepts_by_id,
            problem_types_by_id=problem_types_by_id,
        )
