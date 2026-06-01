"""反馈学习闭环 REST API。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.database import get_db
from poise.core.rbac import CurrentUser, require
from poise.domain.models import BiasCorrection, RollingRun
from poise.feedback.rolling import run_rolling_cycle

router = APIRouter(prefix="/feedback", tags=["feedback"])
DbDep = Annotated[Session, Depends(get_db)]


class RollingTriggerRequest(BaseModel):
    target_week: int = Field(1, ge=1, le=13, description="把第几周视作'刚结束的周'")
    rerun_forecast: bool = True


class RollingRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_id: str
    triggered_at: datetime
    triggered_by: str | None
    week_start: date
    status: str
    forecast_id: str | None
    mape_by_layer: dict[str, Any] | None
    mape_by_category: dict[str, Any] | None
    bias_updates: dict[str, Any] | None
    summary: str | None


class BiasCorrectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category: str
    direction: str
    multiplier: Decimal
    samples: int
    updated_at: datetime


@router.post("/trigger-rolling", response_model=RollingRunOut)
def trigger_rolling(
    body: RollingTriggerRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("plan.solve"))],
) -> RollingRun:
    """手动触发一次滚动重跑（生产环境通过 Celery Beat 每周一 06:00 自动触发）。"""
    result = run_rolling_cycle(
        db,
        entity_id=None,
        target_week=body.target_week,
        rerun_forecast=body.rerun_forecast,
        triggered_by=user.user_id,
    )
    rr = db.get(RollingRun, result.rolling_run_id)
    assert rr is not None
    return rr


@router.get("/rolling-runs", response_model=list[RollingRunOut])
def list_rolling_runs(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
) -> list[RollingRun]:
    stmt = select(RollingRun)
    if entity_id:
        stmt = stmt.where(RollingRun.entity_id == entity_id)
    stmt = stmt.order_by(RollingRun.triggered_at.desc()).limit(limit)
    return list(db.scalars(stmt))


@router.get("/bias-corrections", response_model=list[BiasCorrectionOut])
def list_bias_corrections(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
) -> list[BiasCorrection]:
    stmt = select(BiasCorrection)
    if entity_id:
        stmt = stmt.where(BiasCorrection.entity_id == entity_id)
    return list(db.scalars(stmt.order_by(BiasCorrection.category)))
