"""预测引擎服务层 —— 顶层 run_forecast 编排 + 持久化。

设计要点：
- 全部计算在内存中完成；最后一次性构造 payload 并赋值给 Forecast.payload，
  避免 SQLAlchemy JSON 字段对原地 mutation 不追踪导致的丢失问题。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.data_integration.quality_gate import week_anchor_from_seed
from poise.domain.models import (
    BalanceSnapshot,
    CashFlowItem,
    Forecast,
    ForecastWeek,
    ReserveRule,
)
from poise.forecasting.layered import aggregate_layered, serialize_layered
from poise.forecasting.reserve import compute_min_cash
from poise.forecasting.scenarios import week_band, week_net


def _initial_balance(db: Session, entity_id: str, as_of: date) -> Decimal:
    """取 as_of 日及之前最新的每账户可用余额之和。"""
    balances = db.execute(
        select(BalanceSnapshot)
        .where(BalanceSnapshot.entity_id == entity_id)
        .where(BalanceSnapshot.as_of_date <= as_of)
        .order_by(BalanceSnapshot.as_of_date.desc())
    ).scalars()
    seen: dict[str, BalanceSnapshot] = {}
    for b in balances:
        seen.setdefault(b.account_id, b)
    return sum((b.available_balance for b in seen.values()), Decimal(0))


def run_forecast(
    db: Session,
    entity_id: str,
    as_of: date | None = None,
    horizon: int = 13,
) -> Forecast:
    """生成一份预测并落库。每次调用产出一份新版本。"""

    if as_of is None:
        bs = db.scalar(
            select(BalanceSnapshot)
            .where(BalanceSnapshot.entity_id == entity_id)
            .order_by(BalanceSnapshot.as_of_date)
        )
        as_of = bs.as_of_date if bs else date.today()

    anchor = week_anchor_from_seed(as_of)
    week_dates = [anchor + timedelta(weeks=t - 1) for t in range(1, horizon + 1)]

    cf_items = list(
        db.scalars(select(CashFlowItem).where(CashFlowItem.entity_id == entity_id))
    )
    rule = db.scalar(select(ReserveRule).where(ReserveRule.entity_id == entity_id))

    layered = aggregate_layered(cf_items)
    min_cash = compute_min_cash(cf_items, rule, horizon)
    b0 = _initial_balance(db, entity_id, as_of)
    layer_dump = serialize_layered(layered)

    # 一次性算出两情景的完整序列
    scenarios: dict[str, dict] = {}
    week_rows: list[ForecastWeek] = []  # 留到拿到 forecast.id 后再 add

    for mode in ("neutral", "pessimistic"):
        net_series: list[Decimal] = []
        balance_series: list[Decimal] = []
        cushion_series: list[Decimal] = []
        lower_series: list[Decimal | None] = []
        upper_series: list[Decimal | None] = []
        running = b0
        for t in range(1, horizon + 1):
            wk = layered.get(t)
            net = week_net(wk, mode) if wk else Decimal(0)
            lower, upper = (week_band(wk, mode) if wk else (None, None))
            running += net
            cushion = running - min_cash[t - 1]

            net_series.append(net)
            balance_series.append(running)
            cushion_series.append(cushion)
            lower_series.append(lower)
            upper_series.append(upper)

            week_rows.append(
                ForecastWeek(
                    week_t=t,
                    scenario=mode,
                    net_cash_flow=net,
                    lower_bound=lower,
                    upper_bound=upper,
                    layer_breakdown=layer_dump.get(t),
                )
            )

        scenarios[mode] = {
            "net_cf": [str(v) for v in net_series],
            "balance": [str(v) for v in balance_series],
            "safety_cushion": [str(v) for v in cushion_series],
            "lower_bound": [None if v is None else str(v) for v in lower_series],
            "upper_bound": [None if v is None else str(v) for v in upper_series],
        }

    # 缺口预警分级：
    #   gap_warning_weeks  : 安全垫 < 0           （硬性突破备付底线）
    #   near_breach_weeks  : 0 ≤ 安全垫 < 25% × MinCash（擦边，需关注）
    pess_cushion = scenarios["pessimistic"]["safety_cushion"]
    gap_weeks: list[int] = []
    near_breach_weeks: list[int] = []
    near_threshold_ratio = Decimal("0.25")
    for t, c_raw in enumerate(pess_cushion, start=1):
        c = Decimal(c_raw)
        m = min_cash[t - 1]
        if c < 0:
            gap_weeks.append(t)
        elif m > 0 and c < m * near_threshold_ratio:
            near_breach_weeks.append(t)
    high_finance_dep_weeks: list[int] = []  # Phase 3 求解器接通后填充

    payload = {
        "anchor": anchor.isoformat(),
        "week_dates": [d.isoformat() for d in week_dates],
        "initial_balance": str(b0),
        "min_cash": [str(v) for v in min_cash],
        "scenarios": scenarios,
        "layer_breakdown": {str(k): v for k, v in layer_dump.items()},
        "gap_warning_weeks": gap_weeks,
        "near_breach_weeks": near_breach_weeks,
        "high_finance_dep_weeks": high_finance_dep_weeks,
    }

    forecast = Forecast(
        entity_id=entity_id,
        as_of_date=as_of,
        horizon_weeks=horizon,
        status="ready",
        payload=payload,
    )
    db.add(forecast)
    db.flush()  # 拿到 forecast.id

    for w in week_rows:
        w.forecast_id = forecast.id
        db.add(w)

    db.commit()
    db.refresh(forecast)
    return forecast


def latest_forecast(db: Session, entity_id: str) -> Forecast | None:
    return db.scalar(
        select(Forecast)
        .where(Forecast.entity_id == entity_id)
        .order_by(Forecast.created_at.desc())
    )
