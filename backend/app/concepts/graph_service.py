import logging
from collections import deque
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import CTE, Select

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.concepts.schemas import ConceptRead, ConceptRelationCreate, ConceptRelationRead, PrerequisiteTree
from app.concepts.service import ConceptService
from app.core.exceptions import ApplicationError

logger = logging.getLogger(__name__)


class ConceptGraphService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_direct_prerequisites(self, concept_id: UUID) -> list[Concept]:
        return self._direct(concept_id, RelationType.PREREQUISITE, reverse=True)

    def get_dependents(self, concept_id: UUID) -> list[Concept]:
        """Concepts that directly require the given concept."""
        return self._direct(concept_id, RelationType.PREREQUISITE, reverse=False)

    def get_descendants(
        self, concept_id: UUID, *, relation_type: RelationType = RelationType.PART_OF
    ) -> list[Concept]:
        """All nested parts, or all transitive dependents for PREREQUISITE."""
        self._require_hierarchical(relation_type)
        ConceptService(self.session).get(concept_id)
        reachable = self._reachable(concept_id, relation_type, reverse=relation_type == RelationType.PART_OF)
        query = select(Concept).where(Concept.id.in_(select(reachable.c.id)), Concept.id != concept_id)
        return list(self.session.scalars(self._ordered(query)))

    def get_prerequisite_tree(self, concept_id: UUID) -> PrerequisiteTree:
        ConceptService(self.session).get(concept_id)
        reachable = self._reachable(concept_id, RelationType.PREREQUISITE, reverse=True)
        node_ids = select(reachable.c.id)
        concepts = list(self.session.scalars(self._ordered(select(Concept).where(Concept.id.in_(node_ids)))))
        relations = list(self.session.scalars(
            select(ConceptRelation).where(
                ConceptRelation.relation_type == RelationType.PREREQUISITE,
                ConceptRelation.source_concept_id.in_(node_ids),
                ConceptRelation.target_concept_id.in_(node_ids),
            ).order_by(ConceptRelation.source_concept_id, ConceptRelation.target_concept_id)
        ))
        self._assert_acyclic(concepts, relations)
        return PrerequisiteTree(
            root_concept_id=concept_id,
            concepts=[ConceptRead.model_validate(concept) for concept in concepts],
            relations=[ConceptRelationRead.model_validate(relation) for relation in relations],
        )

    def create_relation(self, data: ConceptRelationCreate) -> ConceptRelation:
        # One transaction lock keeps cycle checks correct across concurrent graph writes.
        # SQLite exists only in tests; production uses PostgreSQL READ COMMITTED.
        self._lock_graph()
        source, target = data.source_concept_id, data.target_concept_id
        concepts = ConceptService(self.session)
        concepts.get(source)
        concepts.get(target)
        if source == target:
            raise ApplicationError(422, "SELF_RELATION", "A concept cannot relate to itself.")
        if data.relation_type == RelationType.RELATED_TO and source > target:
            source, target = target, source
        if self._relation_exists(source, target, data.relation_type):
            raise self._duplicate_relation()
        if data.relation_type != RelationType.RELATED_TO:
            reachable = self._reachable(target, data.relation_type, reverse=False)
            if self.session.scalar(select(reachable.c.id).where(reachable.c.id == source)) is not None:
                raise self._cycle_error()
        relation = ConceptRelation(source_concept_id=source, target_concept_id=target, relation_type=data.relation_type)
        self.session.add(relation)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            if self._relation_exists(source, target, data.relation_type):
                raise self._duplicate_relation() from None
            concepts.get(source)
            concepts.get(target)
            raise
        self.session.refresh(relation)
        logger.info("Concept relation created (relation_id=%s, type=%s)", relation.id, relation.relation_type.value)
        return relation

    def delete_relation(self, relation_id: UUID) -> None:
        self._lock_graph()
        relation = self.session.scalar(
            select(ConceptRelation).where(ConceptRelation.id == relation_id).execution_options(populate_existing=True)
        )
        if relation is None:
            raise ApplicationError(404, "CONCEPT_RELATION_NOT_FOUND", "Concept relation was not found.")
        self.session.delete(relation)
        self.session.commit()
        logger.info("Concept relation deleted (relation_id=%s)", relation_id)

    def _direct(self, concept_id: UUID, relation_type: RelationType, *, reverse: bool) -> list[Concept]:
        ConceptService(self.session).get(concept_id)
        current = ConceptRelation.target_concept_id if reverse else ConceptRelation.source_concept_id
        neighbor = ConceptRelation.source_concept_id if reverse else ConceptRelation.target_concept_id
        query = select(Concept).join(ConceptRelation, Concept.id == neighbor).where(
            current == concept_id, ConceptRelation.relation_type == relation_type
        )
        return list(self.session.scalars(self._ordered(query)))

    def _reachable(self, concept_id: UUID, relation_type: RelationType, *, reverse: bool) -> CTE:
        current = ConceptRelation.target_concept_id if reverse else ConceptRelation.source_concept_id
        neighbor = ConceptRelation.source_concept_id if reverse else ConceptRelation.target_concept_id
        reachable = select(Concept.id.label("id")).where(Concept.id == concept_id).cte("reachable_concepts", recursive=True)
        step = select(neighbor.label("id")).join(reachable, current == reachable.c.id).where(
            ConceptRelation.relation_type == relation_type
        )
        # IDs only + UNION (distinct) terminates even for malformed imported cycles.
        return reachable.union(step)

    @staticmethod
    def _ordered(query: Select[tuple[Concept]]) -> Select[tuple[Concept]]:
        return query.order_by(
            Concept.subject_id, Concept.order_index.nulls_last(), Concept.code, Concept.id
        )

    def _lock_graph(self) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext("edums:concept-graph"))))

    def _relation_exists(self, source: UUID, target: UUID, relation_type: RelationType) -> bool:
        return self.session.scalar(select(ConceptRelation.id).where(
            ConceptRelation.source_concept_id == source,
            ConceptRelation.target_concept_id == target,
            ConceptRelation.relation_type == relation_type,
        )) is not None

    @staticmethod
    def _duplicate_relation() -> ApplicationError:
        return ApplicationError(409, "CONCEPT_RELATION_EXISTS", "Concept relation already exists.")

    @staticmethod
    def _require_hierarchical(relation_type: RelationType) -> None:
        if relation_type not in (RelationType.PREREQUISITE, RelationType.PART_OF):
            raise ApplicationError(422, "INVALID_GRAPH_RELATION_TYPE", "Traversal requires PREREQUISITE or PART_OF.")

    @staticmethod
    def _cycle_error() -> ApplicationError:
        return ApplicationError(409, "CONCEPT_GRAPH_CYCLE", "The concept graph contains or would form a cycle.")

    @classmethod
    def _assert_acyclic(cls, concepts: list[Concept], relations: list[ConceptRelation]) -> None:
        indegree = {concept.id: 0 for concept in concepts}
        outgoing: dict[UUID, list[UUID]] = {concept.id: [] for concept in concepts}
        for relation in relations:
            outgoing[relation.source_concept_id].append(relation.target_concept_id)
            indegree[relation.target_concept_id] += 1
        queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        visited = 0
        while queue:
            visited += 1
            for target in outgoing[queue.popleft()]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        if visited != len(concepts):
            raise cls._cycle_error()
