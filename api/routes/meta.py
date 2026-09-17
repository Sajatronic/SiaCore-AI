from fastapi import APIRouter

from config.settings import settings
from services.event_read import EventReadService

router = APIRouter()
_service = EventReadService()


@router.get("/health")
def health():
    return {"status": "ok", "product": "SiaEye", "platform": "SiaCore"}


@router.get("/meta")
def meta():
    return {
        "product": "SiaEye",
        "platform": "SiaCore",
        "tagline": "Ancient Wisdom. Modern Intelligence.",
        "pipeline_version": settings.pipeline_version,
        "backend": _service.backend,
        "brand": {
            "colors": {
                "navy": "#0D132B",
                "blue": "#2563EB",
                "teal": "#00C2A8",
                "purple": "#7C3AED",
                "magenta": "#D946EF",
                "slate_light": "#64748B",
                "slate_dark": "#94A3B8",
            }
        },
    }
