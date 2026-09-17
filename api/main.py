"""FastAPI application for SiaEye (SiaCore intelligence dashboard)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import alerts, events, meta, stats
from config.settings import settings

app = FastAPI(
    title="SiaEye API",
    description="SiaCore supply chain risk intelligence — read API for end-user dashboards.",
    version=settings.pipeline_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.siaeye_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router, prefix="/api", tags=["meta"])
app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(alerts.router, prefix="/api", tags=["alerts"])


@app.get("/health", include_in_schema=False)
def health_shortcut():
    """Convenience alias for Postman/browser checks at /health."""
    return {"status": "ok", "product": "SiaEye", "platform": "SiaCore", "api_base": "/api"}


@app.get("/api", include_in_schema=False)
def api_root():
    return {
        "product": "SiaEye",
        "platform": "SiaCore",
        "docs": "/docs",
        "health": "/api/health",
        "endpoints": {
            "events": "/api/events",
            "event_detail": "/api/events/{event_id}",
            "summary": "/api/stats/summary",
            "geo": "/api/stats/geo",
            "alerts": "/api/alerts",
            "runs": "/api/runs",
            "meta": "/api/meta",
        },
    }

_frontend_dist = (
    settings.siaeye_frontend_dist
    if settings.siaeye_frontend_dist.is_absolute()
    else settings.project_root / settings.siaeye_frontend_dist
).resolve()
_fallback_static = (Path(__file__).resolve().parent / "static").resolve()
if _frontend_dist.is_dir():
    assets_dir = _frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        requested = _frontend_dist / full_path
        if full_path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(_frontend_dist / "index.html")
elif _fallback_static.is_dir():
    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    @app.get("/", include_in_schema=False)
    async def siaeye_index():
        return FileResponse(_fallback_static / "index.html", headers=_NO_CACHE)

    @app.get("/app.js", include_in_schema=False)
    async def siaeye_app_js():
        return FileResponse(_fallback_static / "app.js", media_type="application/javascript", headers=_NO_CACHE)

    @app.get("/styles.css", include_in_schema=False)
    async def siaeye_styles():
        return FileResponse(_fallback_static / "styles.css", media_type="text/css", headers=_NO_CACHE)

    app.mount("/", StaticFiles(directory=str(_fallback_static), html=True), name="siaeye-static")
