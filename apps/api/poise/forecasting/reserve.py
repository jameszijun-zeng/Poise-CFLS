"""备付金计算（MinCash[t]）。

对应系统设计 §3.5 (C1) 与 §5.2：
- fixed：每周最低备付为常数
- rolling_coverage(N)：MinCash[t] = sum of rigid outflows over [t, t+N-1]

"刚性" 类别：payroll, tax, interest, principal_repay, rent
（采购付款可一定程度弹性，故不纳入；'other' 如并购付款是一次性，也不纳入滚动覆盖）
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from poise.domain.models import CashFlowItem, ReserveRule

RIGID_CATEGORIES = {"payroll", "tax", "interest", "principal_repay", "rent"}


def compute_min_cash(
    items: Iterable[CashFlowItem],
    rule: ReserveRule | None,
    horizon: int = 13,
) -> list[Decimal]:
    """返回 [MinCash[1], MinCash[2], ..., MinCash[horizon]]。"""
    if rule is None:
        return [Decimal(0)] * horizon

    if rule.rule_type == "fixed":
        v = rule.fixed_value or Decimal(0)
        return [v] * horizon

    if rule.rule_type == "rolling_coverage":
        n = rule.rolling_weeks or 4
        rigid_by_week: dict[int, Decimal] = {t: Decimal(0) for t in range(1, horizon + 1)}
        for it in items:
            if it.week_t is None or not 1 <= it.week_t <= horizon:
                continue
            if it.direction != "outflow":
                continue
            if it.category not in RIGID_CATEGORIES:
                continue
            rigid_by_week[it.week_t] += it.amount
        return [
            sum(
                (rigid_by_week.get(k, Decimal(0)) for k in range(t, t + n) if k <= horizon),
                Decimal(0),
            )
            for t in range(1, horizon + 1)
        ]

    return [Decimal(0)] * horizon
