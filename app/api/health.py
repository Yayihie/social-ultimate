from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health():
    return {
        "ok": True,
        "experimental_enabled": settings.experimental_enabled,
        "instagram_configured": bool(settings.instagram_app_id and settings.instagram_app_secret),
    }