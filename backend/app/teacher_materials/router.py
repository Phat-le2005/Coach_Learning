from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from app.ai.dependencies import get_ai_gateway
from app.ai.gateway import AIGateway
from app.auth.dependencies import require_role
from app.core.config import Settings
from app.database.session import get_db
from app.teacher_materials.mapping_service import TeacherMaterialMappingService
from app.teacher_materials.models import MaterialMappingStatus, TeacherMaterialStatus
from app.teacher_materials.schemas import MappingCreate, TeacherMaterialItemRead, TeacherMaterialItemUpdate, TeacherMaterialRead
from app.teacher_materials.service import TeacherMaterialService
from app.teacher_materials.storage import LocalTeacherMaterialStorage
from app.teacher_materials.pdf_import import LocalPdfOcrRunner, TeacherPdfImportService
from app.teacher_materials.pdf_schemas import PdfImportRead, PdfReviewSubmit
from app.users.models import Role, User

router=APIRouter(prefix="/teacher-materials",tags=["Teacher materials"])
Teacher=Annotated[User,Depends(require_role(Role.TEACHER))]

def get_service(request:Request,session:Annotated[Session,Depends(get_db)])->TeacherMaterialService:
    settings:Settings=request.app.state.settings
    return TeacherMaterialService(session,LocalTeacherMaterialStorage(settings.teacher_material_storage_dir),settings.teacher_material_max_bytes)

@router.post("/upload",response_model=TeacherMaterialRead,status_code=201)
async def upload_material(request:Request,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)],file:UploadFile=File(...),classroom_id:UUID=Form(...),subject_id:UUID=Form(...),title:str=Form(...),teaching_plan_id:UUID|None=Form(None))->TeacherMaterialRead:
    settings:Settings=request.app.state.settings
    data=await file.read(settings.teacher_material_max_bytes+1)
    return TeacherMaterialRead.model_validate(service.upload(user.id,classroom_id,subject_id,title,file.filename or "material",file.content_type or "",data,teaching_plan_id))


def get_pdf_service(request: Request, service: Annotated[TeacherMaterialService, Depends(get_service)]) -> TeacherPdfImportService:
    settings = request.app.state.settings
    return TeacherPdfImportService(service, settings.teacher_pdf_import_dir,
        LocalPdfOcrRunner(settings.teacher_pdf_runtime_dir, settings.teacher_pdf_device, settings.teacher_pdf_port))


PdfService = Annotated[TeacherPdfImportService, Depends(get_pdf_service)]


@router.post("/pdf-imports", response_model=PdfImportRead, status_code=202)
async def import_pdf(request: Request, user: Teacher, service: PdfService, file: UploadFile = File(...),
                     classroom_id: UUID = Form(...), subject_id: UUID = Form(...), title: str = Form(...)):
    data = await file.read(request.app.state.settings.teacher_material_max_bytes + 1)
    # Validation and dispatch run off the event loop, alongside other sync services.
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(service.create, user.id, classroom_id, subject_id, title, file.filename or "", data)


@router.get("/pdf-imports", response_model=list[PdfImportRead])
def list_pdf_imports(classroom_id: UUID, user: Teacher, service: PdfService):
    return service.list(user.id, classroom_id)


@router.get("/pdf-imports/{job_id}", response_model=PdfImportRead)
def get_pdf_import(job_id: UUID, user: Teacher, service: PdfService):
    return service.get(user.id, job_id)


@router.post("/pdf-imports/{job_id}/retry", response_model=PdfImportRead)
def retry_pdf_import(job_id: UUID, user: Teacher, service: PdfService):
    return service.retry(user.id, job_id)


@router.post("/pdf-imports/{job_id}/revise", response_model=PdfImportRead, status_code=201)
def revise_pdf_import(job_id: UUID, user: Teacher, service: PdfService):
    return service.revise(user.id, job_id)


@router.put("/pdf-imports/{job_id}/review", response_model=PdfImportRead)
def save_pdf_review(job_id: UUID, data: PdfReviewSubmit, user: Teacher, service: PdfService):
    return service.save_review(user.id, job_id, data)


@router.post("/pdf-imports/{job_id}/submit", response_model=TeacherMaterialRead)
def submit_pdf_import(job_id: UUID, data: PdfReviewSubmit, user: Teacher, service: PdfService):
    return service.submit(user.id, job_id, data)


@router.get("/pdf-imports/{job_id}/source")
def pdf_import_source(job_id: UUID, user: Teacher, service: PdfService):
    source = service.source(user.id, job_id)
    mime = "image/png" if source.suffix == ".png" else "image/jpeg" if source.suffix == ".jpg" else "application/pdf"
    return FileResponse(source, media_type=mime, headers={"Cache-Control": "private, no-store"})


@router.get("/pdf-imports/{job_id}/assets/{index}")
def pdf_import_asset(job_id: UUID, index: int, user: Teacher, service: PdfService):
    return FileResponse(service.asset(user.id, job_id, index), headers={"Cache-Control": "private, no-store"})

@router.get("",response_model=list[TeacherMaterialRead])
def list_materials(classroom_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]): return service.list(user.id,classroom_id)

@router.get("/{material_id}",response_model=TeacherMaterialRead)
def get_material(material_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]): return service.get(user.id,material_id)


@router.delete("/{material_id}", status_code=204)
def delete_material(material_id: UUID, user: Teacher, service: Annotated[TeacherMaterialService, Depends(get_service)]):
    service.archive(user.id, material_id)
    return Response(status_code=204)

@router.get("/{material_id}/items",response_model=list[TeacherMaterialItemRead])
def get_items(material_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]): return service.get(user.id,material_id).items


@router.get("/{material_id}/document")
def download_material(material_id: UUID, user: Teacher, service: Annotated[TeacherMaterialService, Depends(get_service)]):
    material = service.get(user.id, material_id)
    # Generated names only: do not interpolate user-supplied filenames in headers.
    suffix = ".json" if material.mime_type == "application/json" else ".pdf" if material.mime_type == "application/pdf" else ".txt"
    return Response(service.storage.read(material.storage_key), media_type=material.mime_type,
                    headers={"Content-Disposition": f'attachment; filename="material-{material.id}{suffix}"', "Cache-Control": "private, no-store"})


@router.get("/{material_id}/assets/{index}")
def material_visual_asset(material_id: UUID, index: int, user: Teacher, service: PdfService):
    return FileResponse(service.material_asset(user.id, material_id, index), headers={"Cache-Control": "private, no-store"})

@router.patch("/items/{item_id}",response_model=TeacherMaterialItemRead)
def update_item(item_id:UUID,data:TeacherMaterialItemUpdate,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]): return service.update_item(user.id,item_id,data)

@router.post("/{material_id}/map")
async def map_material(material_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)],gateway:Annotated[AIGateway,Depends(get_ai_gateway)]):
    material=service.get(user.id,material_id); mapper=TeacherMaterialMappingService(service.session); results=[]
    for item in material.items:
        if item.extraction_status.value!="ARCHIVED": results.append((await mapper.propose(item,gateway,user.id)).model_dump())
    material.status=TeacherMaterialStatus.MAPPING_PENDING; service.session.commit(); return {"items":results,"mapping_status":"SUGGESTED"}

@router.post("/items/{item_id}/mappings/{kind}",status_code=201)
def add_mapping(item_id:UUID,kind:str,data:MappingCreate,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]):
    row=service.add_mapping(user.id,item_id,kind,data); return {"id":str(row.id),"status":row.status,"source":row.source}

@router.post("/items/{item_id}/mappings/{kind}/{target_id}/confirm")
def confirm_mapping(item_id:UUID,kind:str,target_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]):
    row=service.change_mapping(user.id,item_id,kind,target_id,MaterialMappingStatus.CONFIRMED); return {"id":str(row.id),"status":row.status}

@router.post("/items/{item_id}/mappings/{kind}/{target_id}/reject")
def reject_mapping(item_id:UUID,kind:str,target_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]):
    row=service.change_mapping(user.id,item_id,kind,target_id,MaterialMappingStatus.REJECTED); return {"id":str(row.id),"status":row.status}

@router.post("/items/{item_id}/mappings/problem-types/{target_id}/primary")
def set_primary_problem_type(item_id:UUID,target_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]):
    row=service.set_primary_problem_type(user.id,item_id,target_id); return {"id":str(row.id),"is_primary":row.is_primary}

@router.post("/{material_id}/ready",response_model=TeacherMaterialRead)
def mark_ready(material_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]): return service.mark_ready(user.id,material_id)

@router.post("/{material_id}/prepare-assignment", response_model=TeacherMaterialRead)
def prepare_for_assignment(material_id: UUID, user: Teacher, service: Annotated[TeacherMaterialService, Depends(get_service)]):
    return service.prepare_for_assignment(user.id, material_id)
