"""把 MultiPlanResult 落库到 StrategyPlan + PlanAction。"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from poise.domain.models import Forecast, PlanAction, StrategyPlan
from poise.optimization.multi_plan import MultiPlanResult, PlanCandidate


def persist_plans(db: Session, forecast: Forecast, result: MultiPlanResult) -> list[StrategyPlan]:
    """每个 PlanCandidate 对应一条 StrategyPlan + 多条 PlanAction。"""
    plans: list[StrategyPlan] = []
    for cand in result.candidates:
        plan = StrategyPlan(
            entity_id=forecast.entity_id,
            forecast_id=forecast.id,
            risk_knob=cand.risk_knob,
            status="proposed",
            expected_net_income=cand.expected_net_income,
            safety_cushion_curve=[str(v) for v in cand.safety_cushion_curve],
            gap_warning=bool(cand.gap_warning_weeks),
            high_finance_dep=cand.high_finance_dep,
            summary=cand.summary,
            payload={
                "balance_curve": [str(v) for v in cand.solution.balance_curve],
                "finance_dep_ratio": cand.finance_dep_ratio,
                "gap_warning_weeks": cand.gap_warning_weeks,
                "objective": str(cand.solution.objective) if cand.solution.objective else None,
                "solver_status": cand.solution.status,
            },
        )
        db.add(plan)
        db.flush()  # 拿到 plan.id

        for a in cand.solution.actions:
            db.add(
                PlanAction(
                    plan_id=plan.id,
                    week_t=a.week_t,
                    instrument_id=a.instrument_id,
                    action=a.action,
                    amount=a.amount,
                    tenor_weeks=a.tenor_weeks,
                    notes=f"{a.instrument_kind}:{a.instrument_name}" if a.instrument_name else None,
                )
            )
        plans.append(plan)

    return plans
