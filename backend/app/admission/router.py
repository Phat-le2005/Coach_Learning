import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.admission.ai_schemas import (
    AdmissionAssistantRequest,
    AdmissionAssistantResponse,
)
from app.admission.ai_service import AdmissionAssistantService
from app.admission.import_schemas import (
    AdmissionImportExecuteRequest,
    AdmissionImportHistoryRead,
    AdmissionImportPreviewResponse,
    AdmissionImportResult,
)
from app.admission.import_service import AdmissionImportService
from app.admission.models import AdmissionImportFormat
from app.admission.schemas import (
    AdmissionRuleCreate,
    AdmissionRuleRead,
    AdmissionTargetCreate,
    AdmissionTargetRead,
    AdmissionTargetUpdate,
    MajorCreate,
    MajorRead,
    UniversityCreate,
    UniversityRead,
)
from app.admission.service import AdmissionService
from app.auth.dependencies import get_current_user, require_any_role, require_role
from app.core.errors import ErrorResponse
from app.database.session import get_db
from app.students.service import StudentProfileService
from app.users.models import Role, User

router = APIRouter(
    tags=["Admission Domain"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)

AuthUser = Annotated[User, Depends(get_current_user)]
StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
AdminUser = Annotated[User, Depends(require_any_role(Role.ADMIN))]


def get_admission_service(session: Annotated[Session, Depends(get_db)]) -> AdmissionService:
    return AdmissionService(session)


def get_student_service(session: Annotated[Session, Depends(get_db)]) -> StudentProfileService:
    return StudentProfileService(session)


# --------------------------------------------------------------------------
# Public / Authenticated Admission Catalog Endpoints
# --------------------------------------------------------------------------

@router.get("/admission/universities", response_model=list[UniversityRead])
def list_universities(
    user: AuthUser,
    service: Annotated[AdmissionService, Depends(get_admission_service)],
    search: Annotated[str | None, Query(description="Tìm kiếm theo mã, tên hoặc tên viết tắt")] = None,
    region: Annotated[str | None, Query(description="Lọc theo vùng miền")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[UniversityRead]:
    return service.list_universities(search=search, region=region, offset=offset, limit=limit)


@router.get("/admission/universities/{id}/majors", response_model=list[MajorRead])
def list_majors_by_university(
    id: UUID,
    user: AuthUser,
    service: Annotated[AdmissionService, Depends(get_admission_service)],
    search: Annotated[str | None, Query(description="Tìm kiếm theo mã hoặc tên ngành")] = None,
) -> list[MajorRead]:
    return service.list_majors_by_university(university_id=id, search=search)


@router.get("/admission/majors/{id}/rules", response_model=list[AdmissionRuleRead])
def list_rules_by_major(
    id: UUID,
    user: AuthUser,
    service: Annotated[AdmissionService, Depends(get_admission_service)],
    year: Annotated[int | None, Query(description="Lọc quy chế theo năm tuyển sinh (e.g. 2025, 2026)")] = None,
) -> list[AdmissionRuleRead]:
    return service.list_rules_by_major(major_id=id, year=year)


# --------------------------------------------------------------------------
# Student Admission Targets Endpoints
# --------------------------------------------------------------------------

@router.get("/students/me/admission-targets", response_model=list[AdmissionTargetRead])
def get_my_admission_targets(
    user: StudentUser,
    admission_service: Annotated[AdmissionService, Depends(get_admission_service)],
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
    target_year: Annotated[int | None, Query(description="Lọc theo năm tuyển sinh")] = None,
) -> list[AdmissionTargetRead]:
    profile = student_service.get_for_user(user.id)
    return admission_service.list_student_targets(
        student_profile_id=profile.id, target_year=target_year
    )


@router.post(
    "/students/me/admission-targets",
    response_model=AdmissionTargetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_my_admission_target(
    data: AdmissionTargetCreate,
    user: StudentUser,
    admission_service: Annotated[AdmissionService, Depends(get_admission_service)],
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
) -> AdmissionTargetRead:
    profile = student_service.get_for_user(user.id)
    return admission_service.create_student_target(
        student_profile_id=profile.id, data=data
    )


@router.delete(
    "/students/me/admission-targets/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_my_admission_target(
    id: UUID,
    user: StudentUser,
    admission_service: Annotated[AdmissionService, Depends(get_admission_service)],
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
) -> None:
    profile = student_service.get_for_user(user.id)
    admission_service.delete_student_target(student_profile_id=profile.id, target_id=id)


@router.patch(
    "/students/me/admission-targets/{id}",
    response_model=AdmissionTargetRead,
)
def update_my_admission_target(
    id: UUID,
    data: AdmissionTargetUpdate,
    user: StudentUser,
    admission_service: Annotated[AdmissionService, Depends(get_admission_service)],
    student_service: Annotated[StudentProfileService, Depends(get_student_service)],
) -> AdmissionTargetRead:
    profile = student_service.get_for_user(user.id)
    return admission_service.update_student_target(
        student_profile_id=profile.id, target_id=id, data=data
    )


def get_admission_assistant_service(session: Annotated[Session, Depends(get_db)]) -> AdmissionAssistantService:
    return AdmissionAssistantService(session)


@router.post(
    "/students/me/admission-assistant",
    response_model=AdmissionAssistantResponse,
)
async def consult_admission_assistant(
    user: StudentUser,
    service: Annotated[AdmissionAssistantService, Depends(get_admission_assistant_service)],
    request: AdmissionAssistantRequest | None = None,
) -> AdmissionAssistantResponse:
    return await service.generate_guidance_async(user_id=user.id, request=request)


# --------------------------------------------------------------------------
# Administrative / Seeding Endpoints
# --------------------------------------------------------------------------

@router.post("/admission/universities", response_model=UniversityRead, status_code=status.HTTP_201_CREATED)
def create_university_admin(
    data: UniversityCreate,
    user: AdminUser,
    service: Annotated[AdmissionService, Depends(get_admission_service)],
) -> UniversityRead:
    u = service.create_university(data)
    return UniversityRead(
        id=u.id,
        code=u.code,
        name=u.name,
        short_name=u.short_name,
        description=u.description,
        website=u.website,
        region=u.region,
        is_active=u.is_active,
        majors_count=0,
        created_at=u.created_at,
        updated_at=u.updated_at,
    )


@router.post("/admission/majors", response_model=MajorRead, status_code=status.HTTP_201_CREATED)
def create_major_admin(
    data: MajorCreate,
    user: AdminUser,
    service: Annotated[AdmissionService, Depends(get_admission_service)],
) -> MajorRead:
    m = service.create_major(data)
    return MajorRead.model_validate(m)


@router.post("/admission/rules", response_model=AdmissionRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule_admin(
    data: AdmissionRuleCreate,
    user: AdminUser,
    service: Annotated[AdmissionService, Depends(get_admission_service)],
) -> AdmissionRuleRead:
    r = service.create_rule(data)
    rules = service.list_rules_by_major(major_id=r.major_id, year=r.year)
    for item in rules:
        if item.id == r.id:
            return item
    raise ErrorResponse(code="INTERNAL_ERROR", message="Failed to retrieve created rule")


# --------------------------------------------------------------------------
# Admission Import Pipeline Endpoints
# --------------------------------------------------------------------------

def get_admission_import_service(session: Annotated[Session, Depends(get_db)]) -> AdmissionImportService:
    return AdmissionImportService(session)


@router.post(
    "/admission/import/preview",
    response_model=AdmissionImportPreviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def preview_admission_import_file(
    file: Annotated[UploadFile, File(description="CSV hoặc JSON tệp chứa dữ liệu tuyển sinh")],
    user: AdminUser,
    service: Annotated[AdmissionImportService, Depends(get_admission_import_service)],
) -> AdmissionImportPreviewResponse:
    content = await file.read(AdmissionImportService.MAX_FILE_BYTES + 1)
    await file.close()

    filename = file.filename or "admission_data.csv"
    file_format = AdmissionImportFormat.CSV if filename.lower().endswith(".csv") else AdmissionImportFormat.JSON

    return service.preview(
        actor_id=user.id,
        file_name=filename,
        file_format=file_format,
        content=content,
    )


@router.post(
    "/admission/import/preview-payload",
    response_model=AdmissionImportPreviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def preview_admission_import_payload(
    payload: dict[str, Any] | list[dict[str, Any]],
    user: AdminUser,
    service: Annotated[AdmissionImportService, Depends(get_admission_import_service)],
) -> AdmissionImportPreviewResponse:
    content = json.dumps(payload).encode("utf-8")
    return service.preview(
        actor_id=user.id,
        file_name="direct_payload.json",
        file_format=AdmissionImportFormat.JSON,
        content=content,
    )


@router.post(
    "/admission/import/execute",
    response_model=AdmissionImportResult,
)
def execute_admission_import(
    data: AdmissionImportExecuteRequest,
    user: AdminUser,
    service: Annotated[AdmissionImportService, Depends(get_admission_import_service)],
) -> AdmissionImportResult:
    return service.execute_import(
        batch_id=data.batch_id,
        actor_id=user.id,
        auto_create_entities=data.auto_create_entities,
    )


@router.get(
    "/admission/import/history",
    response_model=list[AdmissionImportHistoryRead],
)
def list_admission_import_history(
    user: AdminUser,
    service: Annotated[AdmissionImportService, Depends(get_admission_import_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[AdmissionImportHistoryRead]:
    return service.list_history(offset=offset, limit=limit)


@router.get(
    "/admission/import/history/{id}",
    response_model=AdmissionImportHistoryRead,
)
def get_admission_import_history_detail(
    id: UUID,
    user: AdminUser,
    service: Annotated[AdmissionImportService, Depends(get_admission_import_service)],
) -> AdmissionImportHistoryRead:
    return service.get_history_detail(history_id=id)
