from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.ai.dependencies import get_ai_gateway
from app.ai.gateway import AIGateway
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.teacher_materials.storage import LocalTeacherMaterialStorage
from app.theory_maps.schemas import TheoryMapRead, TheoryMapSummary, TheoryMapWrite
from app.theory_maps.local_draft import source_page_outline
from app.theory_maps.notebook import notebook_index, notebook_image
from app.theory_maps.service import TheoryMapService
from app.users.models import Role, User

teacher_router = APIRouter(prefix="/teacher/theory", tags=["Teacher theory maps"])
student_router = APIRouter(prefix="/student/theory", tags=["Student theory maps"])
Teacher = Annotated[User, Depends(require_role(Role.TEACHER))]
Student = Annotated[User, Depends(require_role(Role.STUDENT))]


def service(request: Request, db: Annotated[Session, Depends(get_db)]) -> TheoryMapService:
    settings: Settings = request.app.state.settings
    return TheoryMapService(db, LocalTeacherMaterialStorage(settings.teacher_material_storage_dir), settings.teacher_material_max_bytes)


Service = Annotated[TheoryMapService, Depends(service)]


class PublishRequest(BaseModel):
    expected_revision: int = Field(ge=1)


@teacher_router.post("/upload", response_model=TheoryMapRead, status_code=201)
def upload(request: Request, user: Teacher, maps: Service, file: UploadFile = File(...),
           classroom_id: UUID = Form(...), subject_id: UUID = Form(...), title: str = Form(...)):
    max_bytes = request.app.state.settings.teacher_material_max_bytes
    content = file.file.read(max_bytes + 1)
    return maps.upload(user.id, classroom_id, subject_id, title, file.filename or "", content)


@teacher_router.get("", response_model=list[TheoryMapSummary])
def teacher_list(classroom_id: UUID, user: Teacher, maps: Service):
    return maps.teacher_list(user.id, classroom_id)


@teacher_router.get("/{document_id}", response_model=TheoryMapRead)
def teacher_get(document_id: UUID, user: Teacher, maps: Service):
    return maps.teacher_get(user.id, document_id)


@teacher_router.get("/{document_id}/source")
def teacher_source(document_id: UUID, user: Teacher, maps: Service):
    row = maps.teacher_get(user.id, document_id)
    try:
        content = maps.storage.read(row.storage_key)
    except OSError as exc:
        raise ApplicationError(503, "SOURCE_UNAVAILABLE", "Original PDF is unavailable.") from exc
    if sha256(content).hexdigest() != row.sha256:
        raise ApplicationError(503, "SOURCE_HASH_MISMATCH", "Original PDF failed integrity check.")
    return Response(content, media_type="application/pdf", headers={"Cache-Control": "private, no-store", "Content-Disposition": "inline"})


def _verified_source(maps: TheoryMapService, row) -> bytes:
    try:
        content = maps.storage.read(row.storage_key)
    except OSError as exc:
        raise ApplicationError(503, "SOURCE_UNAVAILABLE", "Original PDF is unavailable.") from exc
    if sha256(content).hexdigest() != row.sha256:
        raise ApplicationError(503, "SOURCE_HASH_MISMATCH", "Original PDF failed integrity check.")
    return content


@teacher_router.get("/{document_id}/notebook")
def teacher_notebook(document_id: UUID, user: Teacher, maps: Service):
    row = maps.teacher_get(user.id, document_id)
    return notebook_index(_verified_source(maps, row), row.page_texts)


@teacher_router.get("/{document_id}/notebook/blocks/{page}/{ordinal}")
def teacher_notebook_block(document_id: UUID, page: int, ordinal: int, user: Teacher, maps: Service):
    row = maps.teacher_get(user.id, document_id)
    return Response(
        notebook_image(_verified_source(maps, row), page, ordinal),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@student_router.get("/{document_id}/notebook")
def student_notebook(document_id: UUID, user: Student, maps: Service):
    row = maps.student_source(user.id, document_id)
    return notebook_index(_verified_source(maps, row), row.page_texts)


@student_router.get("/{document_id}/notebook/blocks/{page}/{ordinal}")
def student_notebook_block(document_id: UUID, page: int, ordinal: int, user: Student, maps: Service):
    row = maps.student_source(user.id, document_id)
    return Response(
        notebook_image(_verified_source(maps, row), page, ordinal),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )

@teacher_router.post("/{document_id}/share-source", response_model=TheoryMapRead)
def share_source(document_id: UUID, data: PublishRequest, user: Teacher, maps: Service):
    return maps.set_source_visibility(user.id, document_id, data.expected_revision, visible=True)


@teacher_router.post("/{document_id}/unshare-source", response_model=TheoryMapRead)
def unshare_source(document_id: UUID, data: PublishRequest, user: Teacher, maps: Service):
    return maps.set_source_visibility(user.id, document_id, data.expected_revision, visible=False)


@teacher_router.put("/{document_id}/map", response_model=TheoryMapRead)
def save(document_id: UUID, data: TheoryMapWrite, user: Teacher, maps: Service):
    return maps.save(user.id, document_id, data)


@teacher_router.post("/{document_id}/generate", response_model=TheoryMapRead)
async def generate(document_id: UUID, user: Teacher, maps: Service, gateway: Annotated[AIGateway, Depends(get_ai_gateway)]):
    return await maps.generate_ai(user.id, document_id, gateway=gateway)


@teacher_router.post("/{document_id}/regenerate", response_model=TheoryMapRead)
async def regenerate(document_id: UUID, data: PublishRequest, user: Teacher, maps: Service, gateway: Annotated[AIGateway, Depends(get_ai_gateway)]):
    return await maps.regenerate_ai(user.id, document_id, data.expected_revision, gateway=gateway)


@teacher_router.post("/{document_id}/prefill", response_model=TheoryMapRead)
def prefill(document_id: UUID, data: PublishRequest, user: Teacher, maps: Service):
    return maps.prefill(user.id, document_id, data.expected_revision)


@teacher_router.post("/{document_id}/publish", response_model=TheoryMapRead)
def publish(document_id: UUID, data: PublishRequest, user: Teacher, maps: Service):
    return maps.publish(user.id, document_id, data.expected_revision)


@teacher_router.post("/{document_id}/unpublish", response_model=TheoryMapRead)
def unpublish(document_id: UUID, data: PublishRequest, user: Teacher, maps: Service):
    return maps.unpublish(user.id, document_id, data.expected_revision)


@teacher_router.delete("/{document_id}", status_code=204)
def delete_document(document_id: UUID, user: Teacher, maps: Service):
    maps.delete(user.id, document_id)
    return Response(status_code=204)


@student_router.get("", response_model=list[TheoryMapSummary])
def student_list(user: Student, maps: Service):
    return maps.student_list(user.id)


@student_router.get("/{document_id}", response_model=TheoryMapRead)
def student_get(document_id: UUID, user: Student, maps: Service):
    row = maps.student_get(user.id, document_id)
    result = TheoryMapRead.model_validate(row)
    result.source_outline = source_page_outline(row.page_texts)
    if row.status != "PUBLISHED":
        result.nodes = []
    return result


@student_router.get("/{document_id}/source")
def student_source(document_id: UUID, user: Student, maps: Service):
    row = maps.student_source(user.id, document_id)
    try:
        content = maps.storage.read(row.storage_key)
    except OSError as exc:
        raise ApplicationError(503, "SOURCE_UNAVAILABLE", "Original PDF is unavailable.") from exc
    if sha256(content).hexdigest() != row.sha256:
        raise ApplicationError(503, "SOURCE_HASH_MISMATCH", "Original PDF failed integrity check.")
    return Response(content, media_type="application/pdf", headers={
        "Cache-Control": "private, no-store", "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
    })
