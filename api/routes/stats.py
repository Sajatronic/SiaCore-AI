from fastapi import APIRouter, Query

from services.event_read import EventReadService

router = APIRouter()
_service = EventReadService()


@router.get("/stats/summary")
def summary_stats():
    return _service.summary_stats()


@router.get("/stats/geo")
def geo_stats(min_severity: float = Query(0, ge=0, le=100)):
    return {"points": _service.geo_points(min_severity=min_severity)}
