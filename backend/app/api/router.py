from fastapi import APIRouter

from app.api.health import router as health_router
from app.auth.router import router as auth_router
from app.students.router import router as students_router
from app.teachers.router import router as teachers_router
from app.parents.router import router as parents_router
from app.subjects.router import router as subjects_router
from app.concepts.router import router as concepts_router
from app.classes.router import student_router as student_classes_router
from app.classes.router import teacher_router as teacher_classes_router
from app.questions.router import router as questions_router
from app.curriculum.router import router as curriculum_router
from app.practice.router import router as practice_router
from app.mastery.router import router as mastery_router
from app.digital_twin.router import router as digital_twin_router
from app.diagnostics.router import router as diagnostics_router
from app.planning.router import router as planning_router
from app.learning.router import router as learning_router
from app.ai.admin_router import router as admin_ai_router
from app.ai.tutor_router import router as tutor_router
from app.hints.router import router as hints_router
from app.repair.router import router as repair_router, student_router as adaptive_repair_student_router
from app.assignments.router import (
    student_router as student_assignments_router,
    teacher_router as teacher_assignments_router,
)
from app.exams.router import router as exams_router
from app.admission.router import router as admission_router
from app.tutor.router import router as tutor_memory_router
from app.parents.portal_router import (
    parents_alias_router,
    router as parent_portal_router,
)
from app.teacher_materials.router import router as teacher_materials_router
from app.knowledge_gap.router import router as root_cause_diagnostics_router
from app.question_supply.router import router as question_supply_router
from app.question_acquisition.router import router as question_acquisition_router
from app.question_validation.router import router as question_validation_router


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(students_router)
api_router.include_router(teachers_router)
api_router.include_router(parents_router)
api_router.include_router(subjects_router)
api_router.include_router(concepts_router)
api_router.include_router(curriculum_router)
api_router.include_router(teacher_classes_router)
api_router.include_router(student_classes_router)
api_router.include_router(questions_router)
api_router.include_router(practice_router)
api_router.include_router(repair_router)
api_router.include_router(adaptive_repair_student_router)
api_router.include_router(hints_router)
api_router.include_router(mastery_router)
api_router.include_router(digital_twin_router)
api_router.include_router(diagnostics_router)
api_router.include_router(planning_router)
api_router.include_router(learning_router)
api_router.include_router(admin_ai_router)
api_router.include_router(tutor_router)
api_router.include_router(tutor_memory_router)
api_router.include_router(teacher_assignments_router)
api_router.include_router(student_assignments_router)
api_router.include_router(parent_portal_router)
api_router.include_router(parents_alias_router)
api_router.include_router(exams_router)
api_router.include_router(admission_router)
api_router.include_router(teacher_materials_router)
api_router.include_router(root_cause_diagnostics_router)
api_router.include_router(question_supply_router)
api_router.include_router(question_acquisition_router)
api_router.include_router(question_validation_router)
