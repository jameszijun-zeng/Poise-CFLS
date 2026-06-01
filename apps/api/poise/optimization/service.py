"""Phase 3 决策引擎服务层。

build_and_solve(forecast_id, locks?) → 三档方案落库 + 返回 MultiPlanResult
"""

from __future__ import annotations

import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.audit import record_event
from poise.domain.models import CreditLine, Forecast, Instrument, StrategyPlan
from poise.optimization.multi_plan import MultiPlanResult, generate_plans
from poise.optimization.persist import persist_plans


def build_and_solve(
    db: Session,
    forecast_id: str,
    *,
    locks: dict[int, Decimal] | None = None,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> tuple[MultiPlanResult, list[StrategyPlan]]:
    forecast = db.get(Forecast, forecast_id)
    if forecast is None:
        raise ValueError(f"forecast not found: {forecast_id}")

    instruments = list(
        db.scalars(
            select(Instrument).where(Instrument.entity_id == forecast.entity_id)
        )
    )
    credit_lines = list(
        db.scalars(
            select(CreditLine).where(CreditLine.entity_id == forecast.entity_id)
        )
    )

    t0 = time.perf_counter()
    result = generate_plans(forecast, instruments, credit_lines, locks=locks)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    plans = persist_plans(db, forecast, result)

    record_event(
        db,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        event_type="plan.build_and_solve",
        payload={
            "forecast_id": forecast_id,
            "plan_ids": [p.id for p in plans],
            "candidates": len(result.candidates),
            "infeasibility": result.infeasibility,
            "elapsed_ms": elapsed_ms,
            "locks": {str(k): str(v) for k, v in (locks or {}).items()},
        },
    )
    db.commit()
    for p in plans:
        db.refresh(p)
    return result, plans
