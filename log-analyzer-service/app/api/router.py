from fastapi import APIRouter

from app.api.endpoints import analyze, health, waf_evidence


router = APIRouter()
router.include_router(health.router)
router.include_router(analyze.router)
router.include_router(waf_evidence.router)
