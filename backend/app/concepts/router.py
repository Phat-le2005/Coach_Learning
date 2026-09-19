from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.concepts.graph_service import ConceptGraphService
from app.concepts.models import Concept, ConceptRelation
from app.concepts.schemas import ConceptCreate, ConceptPatch, ConceptRead, ConceptRelationCreate, ConceptRelationRead
from app.concepts.service import ConceptService
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.users.models import Role

router = APIRouter(
    prefix="/admin",
    tags=["Admin concepts"],
    dependencies=[Depends(require_role(Role.ADMIN))],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)


def get_concept_service(session: Annotated[Session, Depends(get_db)]) -> ConceptService:
    return ConceptService(session)


def get_graph_service(session: Annotated[Session, Depends(get_db)]) -> ConceptGraphService:
    return ConceptGraphService(session)


@router.post("/concepts", status_code=201, response_model=ConceptRead)
def create_concept(data: ConceptCreate, service: Annotated[ConceptService, Depends(get_concept_service)]) -> Concept:
    return service.create(data)


@router.patch("/concepts/{id}", response_model=ConceptRead)
def update_concept(id: UUID, data: ConceptPatch, service: Annotated[ConceptService, Depends(get_concept_service)]) -> Concept:
    return service.update(id, data)


@router.post("/concept-relations", status_code=201, response_model=ConceptRelationRead)
def create_relation(
    data: ConceptRelationCreate, service: Annotated[ConceptGraphService, Depends(get_graph_service)]
) -> ConceptRelation:
    return service.create_relation(data)


@router.delete("/concept-relations/{id}", status_code=204, response_class=Response)
def delete_relation(id: UUID, service: Annotated[ConceptGraphService, Depends(get_graph_service)]) -> Response:
    service.delete_relation(id)
    return Response(status_code=204)
