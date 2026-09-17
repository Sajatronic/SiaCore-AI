from fastapi import APIRouter, HTTPException, Query

from services.event_read import EventReadService

router = APIRouter()
_service = EventReadService()


@router.get("/events")
def list_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    category: str | None = None,
    min_severity: float | None = Query(None, ge=0, le=100),
    status: str | None = None,
    search: str | None = None,
    run_id: str | None = None,
):
    return _service.list_events(
        limit=limit,
        offset=offset,
        category=category,
        min_severity=min_severity,
        status=status,
        search=search,
        run_id=run_id,
    )


@router.get("/events/{event_id}")
def get_event(event_id: str):
    event = _service.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/runs")
def list_runs():
    return {"items": _service.list_runs()}
