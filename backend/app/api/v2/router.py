from fastapi import APIRouter

from app.math_solutions.v2_router import router as math_solutions_router
from app.math_ink.router import router as math_ink_router
from app.math_ink.live import router as live_ink_router
from app.math_ink.pairing import owner_router as ink_pairing_router, device_router as ink_device_router
from app.math_ocr.router import router as math_ocr_router
from app.teachers.grading_router import router as teacher_grading_router
from app.teachers.subject_router import router as teacher_subject_router
from app.theory_maps.router import teacher_router as teacher_theory_router, student_router as student_theory_router


api_v2_router = APIRouter()
api_v2_router.include_router(math_solutions_router)
api_v2_router.include_router(math_ink_router)
api_v2_router.include_router(live_ink_router)
api_v2_router.include_router(ink_pairing_router)
api_v2_router.include_router(ink_device_router)
api_v2_router.include_router(math_ocr_router)
api_v2_router.include_router(teacher_subject_router)
api_v2_router.include_router(teacher_grading_router)
api_v2_router.include_router(teacher_theory_router)
api_v2_router.include_router(student_theory_router)
