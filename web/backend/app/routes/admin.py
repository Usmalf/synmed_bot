from fastapi import APIRouter, Depends

from ..deps import require_admin
from ..services.admin_app_service import get_admin_summary

router = APIRouter()


@router.get("/summary")
def admin_summary(session: dict = Depends(require_admin)):
    return get_admin_summary()
