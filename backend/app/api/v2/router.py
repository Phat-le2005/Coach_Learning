from fastapi import APIRouter

from app.math_solutions.v2_router import router as math_solutions_router
from app.math_ink.router import router as math_ink_router


api_v2_router = APIRouter()
api_v2_router.include_router(math_solutions_router)
api_v2_router.include_router(math_ink_router)