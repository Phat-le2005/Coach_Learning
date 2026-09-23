from collections.abc import Callable
from sqlite3 import Cursor
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, event
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.orm import Session

from app.concepts.graph_service import ConceptGraphService
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.concepts.schemas import ConceptCreate, ConceptRelationCreate
from app.concepts.service import ConceptService
from app.core.exceptions import ApplicationError
from app.subjects.models import Subject
from app.subjects.schemas import SubjectCreate
from app.subjects.service import SubjectService

ConceptFactory = Callable[[str, int], Concept]
RelationFactory = Callable[[Concept, Concept, RelationType], ConceptRelation]


def codes(concepts: list[Concept]) -> list[str]:
    return [concept.code for concept in concepts]


def test_direct_queries_follow_prerequisite_direction_and_order(
    graph: ConceptGraphService, concept_factory: ConceptFactory, relation_factory: RelationFactory,
) -> None:
    a, b, c, unrelated = [concept_factory(code, index) for index, code in enumerate(["A", "B", "C", "OTHER"])]
    relation_factory(a, c, RelationType.PREREQUISITE)
    relation_factory(b, c, RelationType.PREREQUISITE)
    relation_factory(c, unrelated, RelationType.PART_OF)
    relation_factory(b, unrelated, RelationType.RELATED_TO)
    assert codes(graph.get_direct_prerequisites(c.id)) == ["A", "B"]
    assert codes(graph.get_dependents(a.id)) == ["C"]
    assert graph.get_direct_prerequisites(a.id) == []
    assert graph.get_dependents(c.id) == []


def test_prerequisite_tree_retains_shared_nodes_all_edges_and_excludes_unrelated(
    graph: ConceptGraphService, concept_factory: ConceptFactory, relation_factory: RelationFactory,
) -> None:
    a, b, c, d, other = [concept_factory(code, index) for index, code in enumerate(["A", "B", "C", "D", "OTHER"])]
    edges = [relation_factory(source, target, RelationType.PREREQUISITE) for source, target in [(a, b), (a, c), (b, d), (c, d)]]
    relation_factory(other, d, RelationType.RELATED_TO)
    relation_factory(other, d, RelationType.PART_OF)
    tree = graph.get_prerequisite_tree(d.id)
    assert tree.root_concept_id == d.id
    assert [node.code for node in tree.concepts] == ["A", "B", "C", "D"]
    assert {edge.id for edge in tree.relations} == {edge.id for edge in edges}
    assert len([node for node in tree.concepts if node.id == a.id]) == 1
    assert codes(graph.get_descendants(a.id, relation_type=RelationType.PREREQUISITE)) == ["B", "C", "D"]
    assert codes(graph.get_dependents(a.id)) == ["B", "C"]


def test_descendants_use_part_of_children_and_do_not_mix_types(
    graph: ConceptGraphService, concept_factory: ConceptFactory, relation_factory: RelationFactory,
) -> None:
    root, chapter, leaf, sibling, other = [concept_factory(code, index) for index, code in enumerate(["ROOT", "CHAPTER", "LEAF", "SIBLING", "OTHER"])]
    relation_factory(chapter, root, RelationType.PART_OF)
    relation_factory(leaf, chapter, RelationType.PART_OF)
    relation_factory(sibling, root, RelationType.PART_OF)
    relation_factory(root, other, RelationType.PREREQUISITE)
    assert codes(graph.get_descendants(root.id)) == ["CHAPTER", "LEAF", "SIBLING"]
    assert codes(graph.get_descendants(chapter.id)) == ["LEAF"]
    assert graph.get_descendants(leaf.id) == []
    assert codes(graph.get_descendants(root.id, relation_type=RelationType.PREREQUISITE)) == ["OTHER"]


def test_isolated_concept_has_empty_neighbors_and_single_node_tree(graph: ConceptGraphService, concept_factory: ConceptFactory) -> None:
    isolated = concept_factory("ISOLATED", 0)
    assert graph.get_direct_prerequisites(isolated.id) == []
    assert graph.get_dependents(isolated.id) == []
    assert graph.get_descendants(isolated.id) == []
    tree = graph.get_prerequisite_tree(isolated.id)
    assert [node.id for node in tree.concepts] == [isolated.id] and tree.relations == []


def test_cross_subject_prerequisites_are_rejected(
    graph: ConceptGraphService, concept_factory: ConceptFactory, db_session: Session,
) -> None:
    """Cross-subject concept relations must be rejected to preserve knowledge graph integrity.

    Concepts belong to a Subject and form a per-subject DAG.  Allowing cross-subject
    prerequisite edges would break the isolation invariant: the knowledge graph for
    Toán cannot declare a dependency on a concept from Ngữ Văn.
    """
    prerequisite = concept_factory("FOUNDATION", 0)
    other_subject = SubjectService(db_session).create(SubjectCreate(code="OTHER", name="Other subject"))
    target = ConceptService(db_session).create(ConceptCreate(
        subject_id=other_subject.id, code="TARGET", name="Target", description="Cross-subject dependency",
        grade_level=12, order_index=0,
    ))
    with pytest.raises(ApplicationError) as error:
        graph.create_relation(
            ConceptRelationCreate(
                source_concept_id=prerequisite.id,
                target_concept_id=target.id,
                relation_type=RelationType.PREREQUISITE,
            )
        )
    assert error.value.status_code == 422
    assert error.value.code == "CROSS_SUBJECT_RELATION"


@pytest.mark.parametrize("method", ["get_direct_prerequisites", "get_dependents", "get_prerequisite_tree", "get_descendants"])
def test_missing_concept_raises_404(graph: ConceptGraphService, method: str) -> None:
    with pytest.raises(ApplicationError) as error:
        getattr(graph, method)(uuid4())
    assert error.value.status_code == 404 and error.value.code == "CONCEPT_NOT_FOUND"


@pytest.mark.parametrize("kind", [RelationType.PREREQUISITE, RelationType.PART_OF])
def test_rejects_short_and_transitive_cycles(
    graph: ConceptGraphService, concept_factory: ConceptFactory, relation_factory: RelationFactory, db_session: Session, kind: RelationType,
) -> None:
    a, b, c = [concept_factory(code, 0) for code in ["A", "B", "C"]]
    relation_factory(a, b, kind)
    relation_factory(b, c, kind)
    for source, target in [(b, a), (c, a)]:
        with pytest.raises(ApplicationError) as error:
            relation_factory(source, target, kind)
        assert error.value.status_code == 409 and error.value.code == "CONCEPT_GRAPH_CYCLE"
        db_session.rollback()
    assert len(graph.get_descendants(a.id, relation_type=RelationType.PREREQUISITE)) == (2 if kind == RelationType.PREREQUISITE else 0)


def test_relations_are_independent_and_related_to_is_symmetric(
    graph: ConceptGraphService, concept_factory: ConceptFactory, relation_factory: RelationFactory, db_session: Session,
) -> None:
    a, b = [concept_factory(code, 0) for code in ["A", "B"]]
    relation_factory(a, b, RelationType.PREREQUISITE)
    relation_factory(b, a, RelationType.PART_OF)
    related = relation_factory(a, b, RelationType.RELATED_TO)
    assert related.source_concept_id < related.target_concept_id
    with pytest.raises(ApplicationError) as error:
        relation_factory(b, a, RelationType.RELATED_TO)
    assert error.value.code == "CONCEPT_RELATION_EXISTS"
    db_session.rollback()
    assert codes(graph.get_direct_prerequisites(b.id)) == ["A"]


@pytest.mark.parametrize("kind", list(RelationType))
def test_rejects_self_relations(graph: ConceptGraphService, concept_factory: ConceptFactory, kind: RelationType) -> None:
    concept = concept_factory("A", 0)
    with pytest.raises(ApplicationError) as error:
        graph.create_relation(ConceptRelationCreate(source_concept_id=concept.id, target_concept_id=concept.id, relation_type=kind))
    assert error.value.status_code == 422 and error.value.code == "SELF_RELATION"


def test_deletion_changes_traversal_immediately(
    graph: ConceptGraphService, concept_factory: ConceptFactory, relation_factory: RelationFactory,
) -> None:
    a, b, c = [concept_factory(code, 0) for code in ["A", "B", "C"]]
    edge = relation_factory(a, b, RelationType.PREREQUISITE)
    relation_factory(b, c, RelationType.PREREQUISITE)
    graph.delete_relation(edge.id)
    assert graph.get_dependents(a.id) == []
    assert codes(graph.get_direct_prerequisites(c.id)) == ["B"]
    assert [node.code for node in graph.get_prerequisite_tree(c.id).concepts] == ["B", "C"]
    with pytest.raises(ApplicationError) as error:
        graph.delete_relation(edge.id)
    assert error.value.code == "CONCEPT_RELATION_NOT_FOUND"


def test_related_to_is_not_a_hierarchy(graph: ConceptGraphService, concept_factory: ConceptFactory) -> None:
    concept = concept_factory("A", 0)
    with pytest.raises(ApplicationError) as error:
        graph.get_descendants(concept.id, relation_type=RelationType.RELATED_TO)
    assert error.value.code == "INVALID_GRAPH_RELATION_TYPE"


def test_imported_cycle_terminates_and_tree_reports_corruption(
    graph: ConceptGraphService, concept_factory: ConceptFactory, db_session: Session,
) -> None:
    a, b, c = [concept_factory(code, 0) for code in ["A", "B", "C"]]
    db_session.add_all([ConceptRelation(source_concept_id=source.id, target_concept_id=target.id, relation_type=RelationType.PREREQUISITE) for source, target in [(a, b), (b, c), (c, a)]])
    db_session.commit()
    assert codes(graph.get_descendants(a.id, relation_type=RelationType.PREREQUISITE)) == ["B", "C"]
    with pytest.raises(ApplicationError) as error:
        graph.get_prerequisite_tree(c.id)
    assert error.value.code == "CONCEPT_GRAPH_CYCLE"


def test_deep_graph_uses_bounded_queries_and_no_python_recursion(
    graph: ConceptGraphService, subject: Subject, db_session: Session, db_engine: Engine,
) -> None:
    # Deeper than the normal Python recursion limit; build via DB for test setup only.
    nodes = [Concept(subject_id=subject.id, code=f"NODE_{index:04}", name=f"Node {index}", description="Synthetic depth test", grade_level=12, order_index=index) for index in range(1100)]
    db_session.add_all(nodes)
    db_session.flush()
    db_session.add_all([ConceptRelation(source_concept_id=source.id, target_concept_id=target.id, relation_type=RelationType.PREREQUISITE) for source, target in zip(nodes, nodes[1:])])
    db_session.commit()
    statements: list[str] = []

    def record(connection: Connection, cursor: Cursor, statement: str, parameters: Any, context: ExecutionContext, executemany: bool) -> None:
        statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", record)
    try:
        tree = graph.get_prerequisite_tree(nodes[-1].id)
        assert len(tree.concepts) == 1100 and len(tree.relations) == 1099
        assert len(statements) <= 4
    finally:
        event.remove(db_engine, "before_cursor_execute", record)
