from fastapi import APIRouter

from services.event_read import EventReadService

router = APIRouter()
_service = EventReadService()


@router.get("/alerts")
def list_alerts():
    """Return high-severity events as alert feed (rule matches when persisted)."""
    result = _service.list_events(limit=200, min_severity=60.0)
    items = []
    for item in result["items"]:
        items.append(
            {
                "event_id": item["event_id"],
                "title": item["title"],
                "severity_score": item["severity_score"],
                "event_category": item["event_category"],
                "geo_country": item["geo_country"],
                "status": item["status"],
            }
        )
    return {"total": len(items), "items": items}
