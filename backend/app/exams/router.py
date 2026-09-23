from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import get_current_user, require_any_role, require_role
from app.core.errors import ErrorResponse
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.exams.ai_explanation_service import ExamAIExplanationService
from app.exams.ai_schemas import ExamAIExplanationRead
from app.exams.analytics_service import ExamAnalyticsService
from app.exams.blueprint_service import ExamBlueprintService
from app.exams.models import Exam, ExamAttempt, ExamSection, ExamStatus, ExamType
from app.exams.schemas import (
    ExamAnalyticsRead,
    ExamAttemptResultRead,
    ExamAttemptStartRead,
    ExamAttemptStatusRead,
    ExamBlueprintConfig,
    ExamCreate,
    ExamDetailRead,
    ExamOptionSanitizedRead,
    ExamQuestionSanitizedRead,
    ExamRead,
    ExamResponseRead,
    ExamResponseSubmitRequest,
    ExamSectionCreate,
    ExamSectionRead,
    ExamUpdate,
)
from app.exams.simulation_service import ExamSimulationService
from app.questions.models import Question
from app.users.models import Role, User

router = APIRouter(
    prefix="/exams",
    tags=["Exam Simulator"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)

TeacherAdminUser = Annotated[User, Depends(require_any_role(Role.TEACHER, Role.ADMIN))]
StudentUser = Annotated[User, Depends(require_role(Role.STUDENT))]
AuthUser = Annotated[User, Depends(get_current_user)]


def get_simulation_service(session: Annotated[Session, Depends(get_db)]) -> ExamSimulationService:
    return ExamSimulationService(session)


def get_blueprint_service(session: Annotated[Session, Depends(get_db)]) -> ExamBlueprintService:
    return ExamBlueprintService(session)


def get_analytics_service(session: Annotated[Session, Depends(get_db)]) -> ExamAnalyticsService:
    return ExamAnalyticsService(session)


def get_ai_explanation_service(session: Annotated[Session, Depends(get_db)]) -> ExamAIExplanationService:
    return ExamAIExplanationService(session)


# --------------------------------------------------------------------------
# Teacher / Admin Management APIs
# --------------------------------------------------------------------------

@router.post(
    "",
    response_model=ExamRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new exam specification",
)
def create_exam(
    payload: ExamCreate,
    user: TeacherAdminUser,
    session: Annotated[Session, Depends(get_db)],
) -> ExamRead:
    bp_dict = payload.blueprint_config.model_dump(mode="json") if payload.blueprint_config else None
    exam = Exam(
        subject_id=payload.subject_id,
        title=payload.title,
        description=payload.description,
        duration_minutes=payload.duration_minutes,
        exam_type=payload.exam_type,
        total_points=payload.total_points,
        passing_score=payload.passing_score,
        blueprint_config=bp_dict,
        status=ExamStatus.DRAFT,
        created_by=user.id,
    )
    session.add(exam)
    session.commit()
    session.refresh(exam)
    return ExamRead.model_validate(exam)


@router.post(
    "/{exam_id}/sections",
    response_model=ExamSectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an exam section with optional section-specific blueprint",
)
def add_exam_section(
    exam_id: UUID,
    payload: ExamSectionCreate,
    user: TeacherAdminUser,
    session: Annotated[Session, Depends(get_db)],
) -> ExamSectionRead:
    exam = session.get(Exam, exam_id)
    if exam is None:
        raise ApplicationError(404, "EXAM_NOT_FOUND", "Exam not found.")

    bp_dict = payload.blueprint_config.model_dump(mode="json") if payload.blueprint_config else None
    section = ExamSection(
        exam_id=exam.id,
        title=payload.title,
        description=payload.description,
        order_index=payload.order_index,
        duration_minutes=payload.duration_minutes,
        section_points=payload.section_points,
        blueprint_config=bp_dict,
    )
    session.add(section)
    session.commit()
    session.refresh(section)
    return ExamSectionRead.model_validate(section)


@router.post(
    "/{exam_id}/generate-from-blueprint",
    response_model=ExamDetailRead,
    summary="Assemble exam questions dynamically from blueprint configuration",
)
def generate_from_blueprint(
    exam_id: UUID,
    user: TeacherAdminUser,
    session: Annotated[Session, Depends(get_db)],
    service: Annotated[ExamBlueprintService, Depends(get_blueprint_service)],
    blueprint_override: ExamBlueprintConfig | None = None,
) -> ExamDetailRead:
    service.assemble_exam_questions(exam_id, blueprint_override)
    session.commit()

    return _get_exam_detail(exam_id, session)


@router.post(
    "/{exam_id}/publish",
    response_model=ExamRead,
    summary="Publish exam to allow students to take simulations",
)
def publish_exam(
    exam_id: UUID,
    user: TeacherAdminUser,
    session: Annotated[Session, Depends(get_db)],
) -> ExamRead:
    exam = session.get(Exam, exam_id)
    if exam is None:
        raise ApplicationError(404, "EXAM_NOT_FOUND", "Exam not found.")

    if exam.total_questions == 0:
        raise ApplicationError(
            400,
            "CANNOT_PUBLISH_EMPTY_EXAM",
            "Exam must have at least 1 question assembled before publishing.",
        )

    exam.status = ExamStatus.PUBLISHED
    exam.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(exam)
    return ExamRead.model_validate(exam)


@router.get(
    "",
    response_model=list[ExamRead],
    summary="List available exams with filtering",
)
def list_exams(
    user: AuthUser,
    session: Annotated[Session, Depends(get_db)],
    subject_id: Annotated[UUID | None, Query(description="Filter by subject ID")] = None,
    status_filter: Annotated[ExamStatus | None, Query(alias="status")] = None,
    exam_type: Annotated[ExamType | None, Query(description="Filter by exam type")] = None,
) -> list[ExamRead]:
    query = select(Exam).order_by(Exam.created_at.desc())

    if user.role == Role.STUDENT:
        # Students can only see published exams
        query = query.where(Exam.status == ExamStatus.PUBLISHED)
    elif status_filter:
        query = query.where(Exam.status == status_filter)

    if subject_id:
        query = query.where(Exam.subject_id == subject_id)
    if exam_type:
        query = query.where(Exam.exam_type == exam_type)

    exams = list(session.scalars(query).all())
    return [ExamRead.model_validate(e) for e in exams]


@router.get(
    "/{exam_id}",
    response_model=ExamDetailRead,
    summary="Get full exam specification and questions",
)
def get_exam_details(
    exam_id: UUID,
    user: AuthUser,
    session: Annotated[Session, Depends(get_db)],
) -> ExamDetailRead:
    return _get_exam_detail(exam_id, session)


# --------------------------------------------------------------------------
# Student Exam Simulator Flow APIs
# --------------------------------------------------------------------------

@router.post(
    "/{exam_id}/start",
    response_model=ExamAttemptStartRead,
    summary="Start an exam simulation attempt",
)
def start_exam(
    exam_id: UUID,
    user: StudentUser,
    service: Annotated[ExamSimulationService, Depends(get_simulation_service)],
    session: Annotated[Session, Depends(get_db)],
) -> ExamAttemptStartRead:
    result = service.start_exam(user.id, exam_id)
    session.commit()
    return result


@router.post(
    "/attempts/{attempt_id}/answer",
    response_model=ExamResponseRead,
    summary="Record student answer during an active exam attempt",
)
def record_response(
    attempt_id: UUID,
    payload: ExamResponseSubmitRequest,
    user: StudentUser,
    service: Annotated[ExamSimulationService, Depends(get_simulation_service)],
    session: Annotated[Session, Depends(get_db)],
) -> ExamResponseRead:
    result = service.record_response(user.id, attempt_id, payload)
    session.commit()
    return result


@router.get(
    "/attempts/{attempt_id}",
    response_model=ExamAttemptStatusRead,
    summary="Check attempt timer, remaining time and answered progress",
)
def check_attempt(
    attempt_id: UUID,
    user: StudentUser,
    service: Annotated[ExamSimulationService, Depends(get_simulation_service)],
    session: Annotated[Session, Depends(get_db)],
) -> ExamAttemptStatusRead:
    result = service.get_attempt_status(user.id, attempt_id)
    session.commit()
    return result


@router.post(
    "/attempts/{attempt_id}/submit",
    response_model=ExamAttemptResultRead,
    summary="Submit exam attempt for deterministic scoring and analytics",
)
def submit_exam(
    attempt_id: UUID,
    user: StudentUser,
    service: Annotated[ExamSimulationService, Depends(get_simulation_service)],
    session: Annotated[Session, Depends(get_db)],
    update_mastery: Annotated[bool, Query(description="Explicit policy flag to pipe evidence into Mastery Engine")] = False,
) -> ExamAttemptResultRead:
    result = service.submit_exam(user.id, attempt_id, update_mastery=update_mastery)
    session.commit()
    return result


@router.get(
    "/attempts/{attempt_id}/analytics",
    response_model=ExamAnalyticsRead,
    summary="Get multi-dimensional diagnostic analytics for a submitted exam",
)
def get_exam_analytics(
    attempt_id: UUID,
    user: AuthUser,
    analytics_service: Annotated[ExamAnalyticsService, Depends(get_analytics_service)],
    session: Annotated[Session, Depends(get_db)],
) -> ExamAnalyticsRead:
    attempt = session.get(ExamAttempt, attempt_id)
    if attempt is None:
        raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Exam attempt not found.")

    if user.role == Role.STUDENT:
        student = session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
        if not student or attempt.student_id != student.id:
            raise ApplicationError(403, "NOT_YOUR_ATTEMPT", "You cannot view another student's exam analytics.")

    return analytics_service.generate_analytics(attempt_id)


# --------------------------------------------------------------------------
# Guardrails Endpoints (REAL_SIMULATION prohibitions)
# --------------------------------------------------------------------------

@router.get(
    "/attempts/{attempt_id}/hint",
    summary="Attempt hint endpoint - blocked in REAL_SIMULATION",
)
def get_attempt_hint(
    attempt_id: UUID,
    user: StudentUser,
    service: Annotated[ExamSimulationService, Depends(get_simulation_service)],
) -> None:
    service.assert_hints_allowed(attempt_id)
    raise ApplicationError(400, "HINT_NOT_APPLICABLE", "Hints are not applicable during exam attempts.")


@router.post(
    "/attempts/{attempt_id}/ai-explanation",
    response_model=ExamAIExplanationRead,
    summary="Generate AI diagnostic explanation for an exam attempt",
)
def generate_attempt_ai_explanation(
    attempt_id: UUID,
    user: AuthUser,
    explanation_service: Annotated[ExamAIExplanationService, Depends(get_ai_explanation_service)],
) -> ExamAIExplanationRead:
    """Generate pedagogical AI explanation for an exam attempt.

    Accessible by:
    - Student owning the attempt.
    - Authorized Teacher of the classroom the student is actively enrolled in.
    - Admin.
    """
    return explanation_service.generate_explanation(attempt_id, user.id)


@router.get(
    "/attempts/{attempt_id}/ai-explanation",
    response_model=ExamAIExplanationRead,
    summary="Retrieve AI diagnostic explanation for an exam attempt",
)
def get_attempt_ai_explanation(
    attempt_id: UUID,
    user: AuthUser,
    explanation_service: Annotated[ExamAIExplanationService, Depends(get_ai_explanation_service)],
) -> ExamAIExplanationRead:
    """Retrieve pedagogical AI explanation for an exam attempt."""
    return explanation_service.generate_explanation(attempt_id, user.id)


# --------------------------------------------------------------------------
# Internal Helpers
# --------------------------------------------------------------------------

def _get_exam_detail(exam_id: UUID, session: Session) -> ExamDetailRead:
    exam = session.scalar(
        select(Exam)
        .options(
            selectinload(Exam.sections),
            selectinload(Exam.questions).selectinload(ExamQuestion.question).selectinload(Question.options),
        )
        .where(Exam.id == exam_id)
    )
    if exam is None:
        raise ApplicationError(404, "EXAM_NOT_FOUND", "Exam not found.")

    sanitized_questions: list[ExamQuestionSanitizedRead] = []
    for eq in exam.questions:
        q = eq.question
        options = [
            ExamOptionSanitizedRead(
                id=opt.id,
                label=opt.label,
                content=opt.content,
                order_index=opt.order_index,
            )
            for opt in q.options
        ]
        sanitized_questions.append(
            ExamQuestionSanitizedRead(
                id=eq.id,
                question_id=eq.question_id,
                section_id=eq.section_id,
                order_index=eq.order_index,
                points=eq.points,
                content=q.content,
                question_type=q.question_type,
                difficulty=q.difficulty,
                cognitive_level=q.cognitive_level,
                options=options,
            )
        )

    sections_read = [
        ExamSectionRead.model_validate(s) for s in exam.sections
    ]

    return ExamDetailRead(
        id=exam.id,
        subject_id=exam.subject_id,
        title=exam.title,
        description=exam.description,
        duration_minutes=exam.duration_minutes,
        status=exam.status,
        exam_type=exam.exam_type,
        total_questions=len(exam.questions),
        total_points=exam.total_points,
        passing_score=exam.passing_score,
        created_by=exam.created_by,
        created_at=exam.created_at,
        updated_at=exam.updated_at,
        sections=sections_read,
        questions=sanitized_questions,
    )
