"""偏差校正系数学习 —— EMA 平滑更新。

对每个 (category, direction)：
    obs_ratio = sum_actual / sum_forecast   （当周聚合）
    new_multiplier = α · obs_ratio + (1 - α) · old_multiplier
α 默认 0.3，给历史一定权重，避免单周抖动主导。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.domain.models import ActualCashFlow, BiasCorrection

EMA_ALPHA = Decimal("0.3")


@dataclass
class BiasUpdate:
    category: str
    direction: str
    obs_ratio: Decimal
    old_multiplier: Decimal
    new_multiplier: Decimal
    samples: int


def update_bias_corrections(
    db: Session,
    entity_id: str,
    actuals: Iterable[ActualCashFlow],
) -> list[BiasUpdate]:
    """读当期 actuals → EMA 更新 BiasCorrection；返回更新列表用于日志。"""
    buckets: dict[tuple[str, str], dict] = defaultdict(lambda: {"f": Decimal(0), "a": Decimal(0), "n": 0})
    for it in actuals:
        k = (it.category, it.direction)
        buckets[k]["f"] += it.forecast_amount
        buckets[k]["a"] += it.actual_amount
        buckets[k]["n"] += 1

    updates: list[BiasUpdate] = []
    for (cat, dir_), agg in buckets.items():
        if agg["f"] <= 0 or agg["n"] == 0:
            continue
        obs_ratio = agg["a"] / agg["f"]
        existing = db.scalar(
            select(BiasCorrection).where(
                BiasCorrection.entity_id == entity_id,
                BiasCorrection.category == cat,
                BiasCorrection.direction == dir_,
            )
        )
        old = existing.multiplier if existing else Decimal(1)
        new = EMA_ALPHA * obs_ratio + (Decimal(1) - EMA_ALPHA) * old
        # 范围保护：避免学到极端系数
        new = max(Decimal("0.5"), min(Decimal("1.5"), new))
        if existing:
            existing.multiplier = new
            existing.samples += agg["n"]
        else:
            db.add(
                BiasCorrection(
                    entity_id=entity_id,
                    category=cat,
                    direction=dir_,
                    multiplier=new,
                    samples=agg["n"],
                )
            )
        updates.append(
            BiasUpdate(
                category=cat, direction=dir_,
                obs_ratio=obs_ratio,
                old_multiplier=old, new_multiplier=new,
                samples=agg["n"],
            )
        )
    db.flush()
    return updates


def get_bias_map(db: Session, entity_id: str) -> dict[tuple[str, str], Decimal]:
    """供预测引擎读取：(category, direction) → multiplier。"""
    rows = db.scalars(
        select(BiasCorrection).where(BiasCorrection.entity_id == entity_id)
    )
    return {(r.category, r.direction): r.multiplier for r in rows}
