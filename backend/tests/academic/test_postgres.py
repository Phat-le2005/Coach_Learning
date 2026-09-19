"""Optional tests on PostgreSQL for recursive SQL and concurrent graph writes."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.concepts.graph_service import ConceptGraphService
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.concepts.schemas import ConceptCreate, ConceptRelationCreate
from app.concepts.service import ConceptService
from app.core.exceptions import ApplicationError
from app.subjects.schemas import SubjectCreate
from app.subjects.service import SubjectService


@pytest.mark.parametrize("kind", [RelationType.PREREQUISITE, RelationType.PART_OF])
def test_concurrent_edges_cannot_form_transitive_cycle(postgres_engine: Engine, kind: RelationType) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False, autoflush=False)
    with factory() as session:
        subject = SubjectService(session).create(SubjectCreate(code="S", name="Subject"))
        nodes = [ConceptService(session).create(ConceptCreate(subject_id=subject.id, code=code, name=code, description="Synthetic concept", grade_level=12, order_index=0)) for code in ["A", "B", "C", "D"]]
        a, b, c, d = [node.id for node in nodes]
        service = ConceptGraphService(session)
        for source, target in [(a, b), (c, d)]:
            service.create_relation(ConceptRelationCreate(source_concept_id=source, target_concept_id=target, relation_type=kind))
    barrier = Barrier(2)

    def create(source: UUID, target: UUID) -> tuple[int, str]:
        with factory() as session:
            # Start both transactions before the graph lock, as auth dependencies do.
            session.scalar(select(Concept.id).limit(1))
            barrier.wait(timeout=10)
            try:
                ConceptGraphService(session).create_relation(ConceptRelationCreate(source_concept_id=source, target_concept_id=target, relation_type=kind))
                return 201, "CREATED"
            except ApplicationError as error:
                session.rollback()
                return error.status_code, error.code
    # Each proposal is safe alone; together B -> C and D -> A would form a cycle.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create, b, c), pool.submit(create, d, a)]
        assert sorted(future.result(timeout=20) for future in futures) == [(201, "CREATED"), (409, "CONCEPT_GRAPH_CYCLE")]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ConceptRelation)) == 3


def test_postgres_recursive_tree_and_descendants_preserve_shared_prerequisite(postgres_engine: Engine) -> None:
    with Session(postgres_engine, expire_on_commit=False) as session:
        subject = SubjectService(session).create(SubjectCreate(code="S", name="Subject"))
        nodes = [ConceptService(session).create(ConceptCreate(subject_id=subject.id, code=code, name=code, description="Synthetic concept", grade_level=12, order_index=index)) for index, code in enumerate(["A", "B", "C", "D"])]
        a, b, c, d = nodes
        graph = ConceptGraphService(session)
        for source, target in [(a, b), (a, c), (b, d), (c, d)]:
            graph.create_relation(ConceptRelationCreate(source_concept_id=source.id, target_concept_id=target.id, relation_type=RelationType.PREREQUISITE))
        tree = graph.get_prerequisite_tree(d.id)
        assert [node.code for node in tree.concepts] == ["A", "B", "C", "D"] and len(tree.relations) == 4
        assert [node.code for node in graph.get_descendants(a.id, relation_type=RelationType.PREREQUISITE)] == ["B", "C", "D"]
