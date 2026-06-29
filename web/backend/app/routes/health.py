from fastapi import APIRouter

from ..services.admin_app_service import list_health_tips

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "synmed-web-api"}


@router.get("/health-tips")
def public_health_tips(audience: str = "landing"):
    return {"tips": list_health_tips(include_inactive=False, audience=audience)}
