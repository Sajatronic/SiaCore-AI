"""HTTP trigger for the existing NexusFlow single-MPN workflow.

Run with:
    uvicorn api:app --host 0.0.0.0 --port 8000

The endpoint runs the existing main.py workflow; it does not duplicate the
scraping or database logic.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
TOKEN = os.getenv("WORKFLOW_TRIGGER_TOKEN", "").strip()
ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("WORKFLOW_ALLOWED_ORIGINS", "*").split(",") if origin.strip()]

app = FastAPI(title="NexusFlow Workflow Trigger", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


class RefreshRequest(BaseModel):
    mpn: str = Field(min_length=1, max_length=160)


def check_token(authorization: str | None, x_workflow_token: str | None) -> None:
    if not TOKEN:
        return
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if bearer != TOKEN and (x_workflow_token or "") != TOKEN:
        raise HTTPException(status_code=401, detail="Invalid workflow token")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/refresh-part")
def refresh_part(
    request: RefreshRequest,
    authorization: str | None = Header(default=None),
    x_workflow_token: str | None = Header(default=None),
) -> dict[str, object]:
    check_token(authorization, x_workflow_token)
    mpn = request.mpn.strip()
    if not re.fullmatch(r"[A-Za-z0-9._+/#()\- ]+", mpn):
        raise HTTPException(status_code=400, detail="Invalid MPN format")

    try:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--mpn", mpn, "--type", "manual"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("WORKFLOW_TIMEOUT_SECONDS", "900")),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Workflow timed out") from None

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Workflow failed")[-4000:]
        raise HTTPException(status_code=502, detail=detail)
    return {"status": "success", "mpn": mpn, "output": (completed.stdout or "")[-4000:]}
