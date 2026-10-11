from fastapi import APIRouter

from app.math_solutions.v2_router import router as math_solutions_router


api_v2_router = APIRouter()
api_v2_router.include_router(math_solutions_router)