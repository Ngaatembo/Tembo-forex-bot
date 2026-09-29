"""Shadow scoreboard: read-only results of the paper-only forward tracking."""

from fastapi import APIRouter, HTTPException

from app.research.shadow_store import load_results

router = APIRouter(prefix="/shadow", tags=["shadow"])


@router.get("/results")
async def shadow_results() -> dict:
    try:
        return await load_results()
    except Exception as exc:  # database unavailable
        raise HTTPException(status_code=503, detail=f"Scoreboard unavailable: {type(exc).__name__}") from exc
