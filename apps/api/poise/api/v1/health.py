from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from poise import __version__
from poise.core.database import get_db
from poise.domain.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:  # noqa: BLE001
        db_status = "down"
    return HealthResponse(status="ok", version=__version__, db=db_status)
