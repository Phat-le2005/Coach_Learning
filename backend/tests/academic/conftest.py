from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.concepts.graph_service import ConceptGraphService
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.concepts.schemas import ConceptCreate, ConceptRelationCreate
from app.concepts.service import ConceptService
from app.core.config import Settings
from app.subjects.models import Subject
from app.subjects.schemas import SubjectCreate
from app.subjects.service import SubjectService
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture
def academic_bearer(db_session: Session, settings: Settings) -> Callable[[Role], dict[str, str]]:
    def headers(role: Role) -> dict[str, str]:
        password = "Synthetic-Academic-Test-Password-2026!"
        user = UserService(db_session).create_user(UserCreate(
            email=f"{role.value.lower()}@example.com", password=password, full_name="Academic Test User", role=role
        ))
        pair = AuthService(db_session, settings).login(LoginRequest(email=user.email, password=password))
        return {"Authorization": f"Bearer {pair.access_token}"}
    return headers


@pytest.fixture
def subject(db_session: Session) -> Subject:
    return SubjectService(db_session).create(SubjectCreate(code="TEST", name="Test subject"))


@pytest.fixture
def concept_factory(db_session: Session, subject: Subject) -> Callable[[str, int], Concept]:
    def create(code: str, order: int = 0) -> Concept:
        return ConceptService(db_session).create(ConceptCreate(
            subject_id=subject.id, code=code, name=f"Concept {code}", description=f"Description {code}",
            grade_level=12, order_index=order,
        ))
    return create


@pytest.fixture
def graph(db_session: Session) -> ConceptGraphService:
    return ConceptGraphService(db_session)


@pytest.fixture
def relation_factory(graph: ConceptGraphService) -> Callable[[Concept, Concept, RelationType], ConceptRelation]:
    def create(source: Concept, target: Concept, kind: RelationType = RelationType.PREREQUISITE) -> ConceptRelation:
        return graph.create_relation(ConceptRelationCreate(
            source_concept_id=source.id, target_concept_id=target.id, relation_type=kind,
        ))
    return create
