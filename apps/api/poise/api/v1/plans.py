"""决策引擎 REST API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.audit import record_event
from poise.core.database import get_db
from poise.core.rbac import CurrentUser, require
from poise.domain.models import Forecast, PlanAction, StrategyPlan
from poise.domain.schemas import (
    BuildAndSolveRequest,
    BuildAndSolveResponse,
    PlanActionOut,
    PlanAdoptRequest,
    StrategyPlanFullOut,
    StrategyPlanOut,
)
from poise.forecasting.service import latest_forecast
from poise.optimization.service import build_and_solve

router = APIRouter(prefix="/plans", tags=["plans"])
DbDep = Annotated[Session, Depends(get_db)]


def _full_view(db: Session, plan: StrategyPlan) -> StrategyPlanFullOut:
    actions = list(
        db.scalars(
            select(PlanAction)
            .where(PlanAction.plan_id == plan.id)
            .order_by(PlanAction.week_t, PlanAction.id)
        )
    )
    return StrategyPlanFullOut(
        id=plan.id,
        entity_id=plan.entity_id,
        forecast_id=plan.forecast_id,
        risk_knob=plan.risk_knob,
        status=plan.status,
        expected_net_income=plan.expected_net_income,
        safety_cushion_curve=plan.safety_cushion_curve,
        gap_warning=plan.gap_warning,
        high_finance_dep=plan.high_finance_dep,
        summary=plan.summary,
        payload=plan.payload,
        created_at=plan.created_at,
        actions=[PlanActionOut.model_validate(a) for a in actions],
    )


@router.post("/build-and-solve", response_model=BuildAndSolveResponse)
def trigger_build_and_solve(
    body: BuildAndSolveRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("plan.solve"))],
) -> BuildAndSolveResponse:
    """触发 build_and_solve：三档求解 + 落库。"""
    forecast_id = body.forecast_id
    if not forecast_id:
        # 取该用户主体的最新预测
        from poise.domain.models import Entity
        ents = list(db.scalars(select(Entity)))
        if len(ents) != 1:
            raise HTTPException(400, "forecast_id 必填（当前主体数 ≠ 1）")
        latest = latest_forecast(db, ents[0].id)
        if not latest:
            raise HTTPException(400, "暂无预测，请先调用 POST /api/v1/forecast/run")
        forecast_id = latest.id

    result, plans = build_and_solve(
        db, forecast_id, locks=body.locks,
        actor_user_id=user.user_id, actor_role=user.role.value,
    )
    return BuildAndSolveResponse(
        forecast_id=forecast_id,
        plan_ids=[p.id for p in plans],
        candidates=[_full_view(db, p) for p in plans],
        infeasibility=result.infeasibility,
    )


@router.get("", response_model=list[StrategyPlanOut])
def list_plans(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
    forecast_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[StrategyPlan]:
    stmt = select(StrategyPlan)
    if entity_id:
        stmt = stmt.where(StrategyPlan.entity_id == entity_id)
    if forecast_id:
        stmt = stmt.where(StrategyPlan.forecast_id == forecast_id)
    stmt = stmt.order_by(StrategyPlan.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


@router.get("/{plan_id}", response_model=StrategyPlanFullOut)
def get_plan(
    plan_id: str,
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
) -> StrategyPlanFullOut:
    plan = db.get(StrategyPlan, plan_id)
    if not plan:
        raise HTTPException(404, "plan not found")
    return _full_view(db, plan)


@router.get("/by-forecast/{forecast_id}", response_model=list[StrategyPlanFullOut])
def list_by_forecast(
    forecast_id: str,
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
) -> list[StrategyPlanFullOut]:
    if not db.get(Forecast, forecast_id):
        raise HTTPException(404, "forecast not found")
    plans = list(
        db.scalars(
            select(StrategyPlan)
            .where(StrategyPlan.forecast_id == forecast_id)
            .order_by(StrategyPlan.created_at.desc())
        )
    )
    # 只取最新一批（每个 risk_knob 取最新一个）
    by_knob: dict[str, StrategyPlan] = {}
    for p in plans:
        by_knob.setdefault(p.risk_knob, p)
    knob_order = {"conservative": 0, "balanced": 1, "aggressive": 2}
    ordered = sorted(by_knob.values(), key=lambda p: knob_order.get(p.risk_knob, 99))
    return [_full_view(db, p) for p in ordered]


@router.post("/{plan_id}/adopt", response_model=StrategyPlanFullOut)
def adopt_plan(
    plan_id: str,
    body: PlanAdoptRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("plan.adopt"))],
) -> StrategyPlanFullOut:
    plan = db.get(StrategyPlan, plan_id)
    if not plan:
        raise HTTPException(404, "plan not found")
    plan.status = "adopted"
    # 同一 forecast 下其他方案标 rejected
    others = list(
        db.scalars(
            select(StrategyPlan)
            .where(StrategyPlan.forecast_id == plan.forecast_id)
            .where(StrategyPlan.id != plan.id)
        )
    )
    for o in others:
        if o.status == "proposed":
            o.status = "rejected"
    record_event(
        db,
        actor_user_id=user.user_id,
        actor_role=user.role.value,
        event_type="plan.adopt",
        payload={"plan_id": plan.id, "risk_knob": plan.risk_knob, "forecast_id": plan.forecast_id},
        notes=body.notes,
    )
    db.commit()
    db.refresh(plan)
    return _full_view(db, plan)


@router.post("/{plan_id}/reject", response_model=StrategyPlanFullOut)
def reject_plan(
    plan_id: str,
    body: PlanAdoptRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("plan.adopt"))],
) -> StrategyPlanFullOut:
    plan = db.get(StrategyPlan, plan_id)
    if not plan:
        raise HTTPException(404, "plan not found")
    plan.status = "rejected"
    record_event(
        db,
        actor_user_id=user.user_id,
        actor_role=user.role.value,
        event_type="plan.reject",
        payload={"plan_id": plan.id, "risk_knob": plan.risk_knob},
        notes=body.notes,
    )
    db.commit()
    db.refresh(plan)
    return _full_view(db, plan)
