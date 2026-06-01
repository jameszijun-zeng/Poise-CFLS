"""MAPE 计算 —— 基于 ActualCashFlow 表。

MAPE = mean(|actual - forecast| / |actual|) × 100%
返回结构便于落 RollingRun.mape_by_layer / mape_by_category。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from poise.domain.models import ActualCashFlow


@dataclass
class MapeBucket:
    key: str
    samples: int = 0
    sum_abs_pct_err: Decimal = Decimal(0)

    @property
    def mape(self) -> Decimal | None:
        if self.samples == 0:
            return None
        return self.sum_abs_pct_err / Decimal(self.samples)


@dataclass
class MapeResult:
    by_layer: dict[str, MapeBucket] = field(default_factory=dict)
    by_category: dict[str, MapeBucket] = field(default_factory=dict)
    by_layer_category: dict[tuple[str, str], MapeBucket] = field(default_factory=dict)

    def as_payload(self) -> dict:
        return {
            "by_layer": [
                {"layer": b.key, "sample_count": b.samples, "mape": str(b.mape) if b.mape is not None else None}
                for b in self.by_layer.values()
            ],
            "by_category": [
                {"category": b.key, "sample_count": b.samples, "mape": str(b.mape) if b.mape is not None else None}
                for b in self.by_category.values()
            ],
        }


def compute_mape(actuals: Iterable[ActualCashFlow]) -> MapeResult:
    """对一组 (forecast, actual) 计算分层 / 分类 MAPE。

    保护：当 actual_amount == 0 时跳过该样本（避免除零）。
    """
    res = MapeResult()
    for a in actuals:
        if a.actual_amount == 0:
            continue
        err = abs(a.actual_amount - a.forecast_amount) / abs(a.actual_amount)
        # 分层
        b = res.by_layer.setdefault(a.certainty_layer, MapeBucket(a.certainty_layer))
        b.samples += 1
        b.sum_abs_pct_err += err
        # 分类
        b2 = res.by_category.setdefault(a.category, MapeBucket(a.category))
        b2.samples += 1
        b2.sum_abs_pct_err += err
        # 复合 key
        ck = (a.certainty_layer, a.category)
        b3 = res.by_layer_category.setdefault(ck, MapeBucket(f"{a.certainty_layer}/{a.category}"))
        b3.samples += 1
        b3.sum_abs_pct_err += err
    return res
