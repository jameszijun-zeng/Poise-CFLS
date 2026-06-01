"""分层聚合 —— 按 (week_t × certainty_layer × direction) 汇总现金流项。

对应系统设计 §4.1：
- 确定层（W1–4）：来自 contract/ar/ap/schedule 的逐笔
- 规律层（W5–8）：账龄/季节统计驱动
- 不确定层（W9–13）：业务驱动 + 区间

Phase 2 MVP：来自 CashFlowItem.certainty_layer 字段直接路由；
未来若引入时序模型/账龄模型，仅替换 `_pattern_layer` / `_uncertain_layer` 内部，
对外接口不变。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from poise.domain.models import CashFlowItem

LAYERS = ("deterministic", "pattern", "uncertain")
DIRECTIONS = ("inflow", "outflow")

# 不确定层区间默认 ±20%（无历史时的兜底）
UNCERTAIN_DEFAULT_WIDTH = Decimal("0.20")


@dataclass
class LayerCell:
    inflow: Decimal = Decimal(0)
    outflow: Decimal = Decimal(0)
    items: list[str] = field(default_factory=list)  # item ids

    @property
    def net(self) -> Decimal:
        return self.inflow - self.outflow


@dataclass
class WeekLayered:
    week_t: int
    by_layer: dict[str, LayerCell] = field(default_factory=lambda: {layer: LayerCell() for layer in LAYERS})

    @property
    def inflow(self) -> Decimal:
        return sum((c.inflow for c in self.by_layer.values()), Decimal(0))

    @property
    def outflow(self) -> Decimal:
        return sum((c.outflow for c in self.by_layer.values()), Decimal(0))

    @property
    def net(self) -> Decimal:
        return self.inflow - self.outflow

    def uncertain_band(self) -> tuple[Decimal, Decimal]:
        """uncertain 层 ± UNCERTAIN_DEFAULT_WIDTH 作为不确定区间。
        其它层不参与（视为点值）。返回 (lower, upper) 相对总 net 的绝对值。"""
        u = self.by_layer["uncertain"]
        band_in = u.inflow * UNCERTAIN_DEFAULT_WIDTH
        band_out = u.outflow * UNCERTAIN_DEFAULT_WIDTH
        # 收入向下、支出向上时净额向下；反之向上
        lower = self.net - band_in - band_out
        upper = self.net + band_in + band_out
        return lower, upper


def aggregate_layered(items: Iterable[CashFlowItem]) -> dict[int, WeekLayered]:
    """按 week_t 聚合 CashFlowItem，仅纳入 1..13 周。"""
    by_week: dict[int, WeekLayered] = defaultdict(lambda: WeekLayered(week_t=0))
    for it in items:
        if it.week_t is None or not 1 <= it.week_t <= 13:
            continue
        layer = it.certainty_layer
        if layer not in LAYERS:
            continue
        wk = by_week[it.week_t]
        wk.week_t = it.week_t
        cell = wk.by_layer[layer]
        if it.direction == "inflow":
            cell.inflow += it.amount
        elif it.direction == "outflow":
            cell.outflow += it.amount
        cell.items.append(it.id)
    return dict(by_week)


def serialize_layered(by_week: dict[int, WeekLayered]) -> dict[int, dict]:
    """转 JSON 友好结构，便于落 ForecastWeek.layer_breakdown。"""
    out: dict[int, dict] = {}
    for t, wk in by_week.items():
        out[t] = {
            layer: {
                "inflow": str(cell.inflow),
                "outflow": str(cell.outflow),
                "net": str(cell.net),
                "items": cell.items,
            }
            for layer, cell in wk.by_layer.items()
        }
    return out
