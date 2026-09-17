#!/usr/bin/env python3
"""Launch the SiaEye API (SiaCore intelligence dashboard backend)."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

from config.settings import settings

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=settings.siaeye_api_host,
        port=settings.siaeye_api_port,
        reload=True,
    )
