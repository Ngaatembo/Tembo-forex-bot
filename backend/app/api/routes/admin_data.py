"""
TEMPORARY admin-only download endpoint for Experiment 3's post-2022
research data (Render's filesystem has no other path into this
sandbox — see the export script's own docstring). Strictly read-only.

REMOVE THIS FILE, its router registration in main.py, and the
ADMIN_DOWNLOAD_TOKEN setting once Experiment 3's data has been
retrieved. This is not meant to be permanent infrastructure.

SECURITY DESIGN:
- No directory-listing endpoint exists anywhere — only single-file
  GET-by-exact-name.
- Filenames are checked against a hardcoded allowlist (ALLOWED_FILENAMES).
  Path traversal is structurally impossible, not just filtered: any
  string that isn't an EXACT match to one of the 7 known filenames is
  rejected before any filesystem path is even constructed, regardless
  of what characters it contains.
- Auth: a static bearer token compared against ADMIN_DOWNLOAD_TOKEN.
  No real wired-in auth/admin system exists elsewhere in this codebase
  to reuse (app/core/security.py's own docstring: JWT/password
  scaffolding only, never wired into any route) — this is a
  deliberately separate, minimal secret from SECRET_KEY (which exists
  for JWT signing; reusing a signing key as a bearer-comparison token
  would weaken it). Fails closed (403) if ADMIN_DOWNLOAD_TOKEN is unset.
- Only serves files that actually exist (404 otherwise) — never
  fabricates or creates anything.
- Never logs the token or file contents.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse

from app.core.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin-temporary"])

DATA_DIR = str(Path(__file__).resolve().parents[4] / "research" / "data" / "post_2022")

ALLOWED_FILENAMES = frozenset({
    "EURUSD_H1_2023plus.csv", "GBPUSD_H1_2023plus.csv", "XAUUSD_H1_2023plus.csv",
    "EURUSD_H1_2023plus_metadata.json", "GBPUSD_H1_2023plus_metadata.json", "XAUUSD_H1_2023plus_metadata.json",
    "export_summary.json",
})

_MEDIA_TYPES = {".csv": "text/csv", ".json": "application/json"}


def _require_admin_token(authorization: str = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.admin_download_token:
        raise HTTPException(status_code=403, detail="Admin download endpoint is not configured.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    provided = authorization.removeprefix("Bearer ").strip()
    if provided != settings.admin_download_token:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


@router.get("/research-data/{filename}")
async def download_research_data_file(filename: str, authorization: str = Header(default=None)):
    _require_admin_token(authorization)

    if filename not in ALLOWED_FILENAMES:
        raise HTTPException(status_code=403, detail="Filename is not in the allowed list.")

    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found.")

    ext = os.path.splitext(filename)[1]
    return FileResponse(path=file_path, media_type=_MEDIA_TYPES.get(ext, "application/octet-stream"), filename=filename)
