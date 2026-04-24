from fastapi import APIRouter

from app.api.endpoints.console_frontend import router as console_frontend_router
from app.api.endpoints.home import router as home_router
from app.api.endpoints.health import router as health_router
from app.api.endpoints.tasks import router as task_router
from app.api.endpoints.waf_audit_frontend import router as waf_audit_frontend_router
from app.api.endpoints.waf_audits import router as waf_audit_router
from app.api.endpoints.waf_frontend import router as waf_frontend_router
from app.api.endpoints.waf_preprocessing import router as waf_preprocessing_router
from app.api.endpoints.waf_trend_enhancements import router as waf_trend_enhancement_router
from app.api.endpoints.xray_frontend import router as xray_frontend_router


api_router = APIRouter()
api_router.include_router(home_router, tags=["home"])
api_router.include_router(console_frontend_router, tags=["console-ui"])
api_router.include_router(health_router, tags=["health"])
api_router.include_router(task_router, tags=["tasks"])
api_router.include_router(waf_audit_frontend_router, tags=["waf-audit-ui"])
api_router.include_router(waf_audit_router, tags=["waf-audits"])
api_router.include_router(waf_frontend_router, tags=["waf-ui"])
api_router.include_router(waf_preprocessing_router, tags=["waf-preprocessing"])
api_router.include_router(waf_trend_enhancement_router, tags=["waf-trend-enhancements"])
api_router.include_router(xray_frontend_router, tags=["xray-ui"])
