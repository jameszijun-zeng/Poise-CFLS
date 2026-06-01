"""每周一 06:00 滚动重跑编排（系统设计 §4.3）。

完整流程：
1. 取当前 anchor 周（"上一周"）的 forecast 与对应 CashFlowItem
2. 生成 / 收集"实际值"快照（demo 用合成数据；生产连银企直连）
3. 计算 MAPE（分层 + 分类）
4. EMA 更新 BiasCorrection
5. （可选）触发新一轮 run_forecast + build_and_solve
6. 落 RollingRun 记录 + AuditLog

不依赖 Celery 即可手动调；Celery Beat 仅做定时触发。
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.audit import record_event
from poise.domain.models import (
    ActualCashFlow,
    CashFlowItem,
    Entity,
    Forecast,
    RollingRun,
)
from poise.feedback.bias import update_bias_corrections
from poise.feedback.mape import compute_mape
from poise.forecasting.service import latest_forecast, run_forecast


@dataclass
class RollingResult:
    rolling_run_id: str
    week_start: date
    new_forecast_id: str | None
    actual_rows: int
    mape_by_layer: dict
    mape_by_category: dict
    bias_updates_count: int
    elapsed_ms: int


def _synthetic_actuals(
    db: Session,
    entity_id: str,
    target_week: int,
    forecast: Forecast,
) -> list[ActualCashFlow]:
    """为 demo 生成"实际值"快照：基于该周 CashFlowItem 的 forecast 值 ± 随机扰动。

    扰动幅度按 certainty_layer：
      deterministic ±2%, pattern ±8%, uncertain ±18%
    扰动使用确定性哈希（entity_id + week_t + item.id），保证可复现。
    """
    cf_items = list(
        db.scalars(
            select(CashFlowItem)
            .where(CashFlowItem.entity_id == entity_id)
            .where(CashFlowItem.week_t == target_week)
        )
    )
    if not cf_items:
        return []

    anchor_iso = forecast.as_of_date.isoformat()
    week_dates = (forecast.payload or {}).get("week_dates", [])
    week_start = (
        date.fromisoformat(week_dates[target_week - 1])
        if week_dates and target_week - 1 < len(week_dates)
        else forecast.as_of_date + timedelta(weeks=target_week - 1)
    )

    bands = {"deterministic": 0.02, "pattern": 0.08, "uncertain": 0.18}

    actuals: list[ActualCashFlow] = []
    for it in cf_items:
        band = bands.get(it.certainty_layer, 0.1)
        # 确定性"随机"：哈希落到 [-1, 1)
        h = hashlib.md5(f"{anchor_iso}|{target_week}|{it.id}".encode()).digest()
        bias = (int.from_bytes(h[:4], "big") / (2**32)) * 2 - 1
        factor = Decimal(str(round(1.0 + band * bias, 6)))
        actual = it.amount * factor
        actuals.append(
            ActualCashFlow(
                entity_id=entity_id,
                week_start=week_start,
                direction=it.direction,
                category=it.category,
                certainty_layer=it.certainty_layer,
                forecast_amount=it.amount,
                actual_amount=actual,
                source="synthetic",
            )
        )
    for a in actuals:
        db.add(a)
    db.flush()
    return actuals


def run_rolling_cycle(
    db: Session,
    entity_id: str | None = None,
    *,
    target_week: int = 1,
    rerun_forecast: bool = True,
    triggered_by: str | None = None,
) -> RollingResult:
    """执行一次完整滚动周期。"""
    t0 = time.perf_counter()
    if entity_id is None:
        ents = list(db.scalars(select(Entity)))
        if not ents:
            raise ValueError("无 entity，无法滚动")
        entity_id = ents[0].id

    fc = latest_forecast(db, entity_id)
    if fc is None:
        fc = run_forecast(db, entity_id)

    # 1. 生成 / 取实际值
    actuals = _synthetic_actuals(db, entity_id, target_week, fc)

    # 2. MAPE
    mape = compute_mape(actuals)

    # 3. EMA 偏差校正
    bias_updates = update_bias_corrections(db, entity_id, actuals)

    # 4. （可选）新一轮预测
    new_fc_id: str | None = None
    if rerun_forecast:
        new_fc = run_forecast(db, entity_id)
        new_fc_id = new_fc.id

    # 5. RollingRun 落库
    week_dates = (fc.payload or {}).get("week_dates", [])
    week_start = (
        date.fromisoformat(week_dates[target_week - 1])
        if week_dates and target_week - 1 < len(week_dates)
        else fc.as_of_date + timedelta(weeks=target_week - 1)
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    payload = mape.as_payload()
    bias_payload = [
        {
            "category": u.category,
            "direction": u.direction,
            "obs_ratio": str(u.obs_ratio),
            "old": str(u.old_multiplier),
            "new": str(u.new_multiplier),
            "samples": u.samples,
        }
        for u in bias_updates
    ]
    summary = (
        f"滚动周 W{target_week} · 实际 {len(actuals)} 笔 · "
        f"MAPE 分层 {len(payload['by_layer'])} 桶 / 分类 {len(payload['by_category'])} 桶 · "
        f"偏差更新 {len(bias_updates)} 项 · "
        f"耗时 {elapsed_ms} ms"
        + (f" · 新预测 {new_fc_id[:8]}..." if new_fc_id else "")
    )
    rr = RollingRun(
        entity_id=entity_id,
        triggered_by=triggered_by or "scheduler",
        week_start=week_start,
        status="completed",
        forecast_id=new_fc_id or fc.id,
        mape_by_layer={"items": payload["by_layer"]},
        mape_by_category={"items": payload["by_category"]},
        bias_updates={"items": bias_payload},
        summary=summary,
    )
    db.add(rr)
    db.flush()

    record_event(
        db,
        actor_user_id=triggered_by,
        actor_role="scheduler" if triggered_by is None else None,
        event_type="feedback.rolling_run",
        payload={
            "rolling_run_id": rr.id,
            "entity_id": entity_id,
            "target_week": target_week,
            "actual_rows": len(actuals),
            "bias_updates": len(bias_updates),
            "new_forecast_id": new_fc_id,
            "elapsed_ms": elapsed_ms,
        },
        notes=summary,
    )
    db.commit()
    db.refresh(rr)

    return RollingResult(
        rolling_run_id=rr.id,
        week_start=week_start,
        new_forecast_id=new_fc_id,
        actual_rows=len(actuals),
        mape_by_layer=payload["by_layer"],
        mape_by_category=payload["by_category"],
        bias_updates_count=len(bias_updates),
        elapsed_ms=elapsed_ms,
    )
