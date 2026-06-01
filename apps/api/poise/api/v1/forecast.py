"""预测引擎 REST API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.audit import record_event
from poise.core.database import get_db
from poise.core.rbac import CurrentUser, require
from poise.domain.models import Entity, Forecast, ForecastWeek
from poise.domain.schemas import (
    AccuracyOut,
    ForecastFullOut,
    ForecastOut,
    ForecastRunRequest,
    ForecastWeekOut,
)
from poise.forecasting.accuracy import empty_accuracy_payload
from poise.forecasting.service import latest_forecast, run_forecast

router = APIRouter(prefix="/forecast", tags=["forecast"])

DbDep = Annotated[Session, Depends(get_db)]


def _resolve_entity_id(db: Session, given: str | None) -> str:
    if given:
        if not db.get(Entity, given):
            raise HTTPException(404, f"entity not found: {given}")
        return given
    ents = list(db.scalars(select(Entity)))
    if len(ents) != 1:
        raise HTTPException(400, "entity_id 必填（当前主体数 ≠ 1）")
    return ents[0].id


@router.post("/run", response_model=ForecastFullOut)
def trigger_run(
    body: ForecastRunRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("forecast.run"))],
) -> ForecastFullOut:
    entity_id = _resolve_entity_id(db, body.entity_id)
    forecast = run_forecast(db, entity_id, body.as_of, body.horizon_weeks)
    record_event(
        db,
        actor_user_id=user.user_id,
        actor_role=user.role.value,
        event_type="forecast.run",
        payload={
            "forecast_id": forecast.id,
            "entity_id": entity_id,
            "as_of": forecast.as_of_date.isoformat(),
            "horizon": forecast.horizon_weeks,
            "gap_warning_weeks": (forecast.payload or {}).get("gap_warning_weeks", []),
        },
    )
    db.commit()
    return _full_view(db, forecast)


@router.get("/latest", response_model=ForecastFullOut | None)
def get_latest(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
) -> ForecastFullOut | None:
    eid = _resolve_entity_id(db, entity_id)
    forecast = latest_forecast(db, eid)
    if not forecast:
        return None
    return _full_view(db, forecast)


@router.get("/{forecast_id}", response_model=ForecastFullOut)
def get_one(
    forecast_id: str,
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
) -> ForecastFullOut:
    forecast = db.get(Forecast, forecast_id)
    if not forecast:
        raise HTTPException(404, "forecast not found")
    return _full_view(db, forecast)


@router.get("", response_model=list[ForecastOut])
def list_forecasts(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> list[Forecast]:
    stmt = select(Forecast)
    if entity_id:
        stmt = stmt.where(Forecast.entity_id == entity_id)
    stmt = stmt.order_by(Forecast.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


@router.get("/accuracy/summary", response_model=AccuracyOut)
def get_accuracy(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
) -> dict:
    """聚合所有 ActualCashFlow 计算实时 MAPE；无数据时返回空骨架。"""
    from poise.domain.models import ActualCashFlow
    from poise.feedback.mape import compute_mape

    stmt = select(ActualCashFlow)
    if entity_id:
        stmt = stmt.where(ActualCashFlow.entity_id == entity_id)
    actuals = list(db.scalars(stmt))
    if not actuals:
        return empty_accuracy_payload()
    mape = compute_mape(actuals)
    payload = mape.as_payload()
    payload["note"] = f"基于 {len(actuals)} 个 (forecast, actual) 样本对计算。"
    return payload


def _full_view(db: Session, forecast: Forecast) -> ForecastFullOut:
    weeks = list(
        db.scalars(
            select(ForecastWeek)
            .where(ForecastWeek.forecast_id == forecast.id)
            .order_by(ForecastWeek.week_t, ForecastWeek.scenario)
        )
    )
    return ForecastFullOut(
        id=forecast.id,
        entity_id=forecast.entity_id,
        as_of_date=forecast.as_of_date,
        horizon_weeks=forecast.horizon_weeks,
        status=forecast.status,
        payload=forecast.payload,
        created_at=forecast.created_at,
        weeks=[ForecastWeekOut.model_validate(w) for w in weeks],
    )
