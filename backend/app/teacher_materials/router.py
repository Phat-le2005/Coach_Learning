from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
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

@router.get("",response_model=list[TeacherMaterialRead])
def list_materials(classroom_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]): return service.list(user.id,classroom_id)

@router.get("/{material_id}",response_model=TeacherMaterialRead)
def get_material(material_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]): return service.get(user.id,material_id)

@router.get("/{material_id}/items",response_model=list[TeacherMaterialItemRead])
def get_items(material_id:UUID,user:Teacher,service:Annotated[TeacherMaterialService,Depends(get_service)]): return service.get(user.id,material_id).items

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
