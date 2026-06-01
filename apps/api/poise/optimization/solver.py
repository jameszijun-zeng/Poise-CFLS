"""求解器封装 —— HiGHS 默认 / CBC 兜底；返回结构化 Solution。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pulp

from poise.core.config import get_settings
from poise.optimization.model import ModelHandles

# 求解状态枚举（与 PuLP 对齐）
STATUS_LABELS = {
    pulp.LpStatusOptimal: "optimal",
    pulp.LpStatusNotSolved: "not_solved",
    pulp.LpStatusInfeasible: "infeasible",
    pulp.LpStatusUnbounded: "unbounded",
    pulp.LpStatusUndefined: "undefined",
}


@dataclass
class PlanAction:
    week_t: int
    instrument_id: str
    action: str          # invest / repay / draw / redeem
    amount: Decimal
    tenor_weeks: int | None = None
    instrument_name: str | None = None
    instrument_kind: str | None = None


@dataclass
class Solution:
    status: str
    objective: Decimal | None
    actions: list[PlanAction] = field(default_factory=list)
    balance_curve: list[Decimal] = field(default_factory=list)  # B[1..H]
    slack_curve: list[Decimal] = field(default_factory=list)    # 仅 with_slack 时填
    finance_dep_ratio: float = 0.0  # 总融资动用 / 总授信可用
    raw: dict[str, Any] = field(default_factory=dict)


def _pick_solver(time_limit_sec: int) -> pulp.LpSolver:
    """选择求解器。
    SOLVER_BACKEND=highs：尝试 pulp.HiGHS(highspy)；当前 pulp 3.3.2 + highspy 1.14
    在解析含 binary 决策的约束 slack 时偶发 IndexError，需要 .env 显式启用。
    默认走 CBC（PULP_CBC_CMD，pulp 内置，稳定可靠）。
    """
    backend = get_settings().solver_backend
    if backend == "highs" and "HiGHS" in pulp.listSolvers(onlyAvailable=True):
        return pulp.HiGHS(msg=False, timeLimit=time_limit_sec)
    return pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_sec)


def solve(handles: ModelHandles, *, time_limit_sec: int | None = None) -> Solution:
    """求解并把变量值解析成结构化 Solution。"""
    settings = get_settings()
    solver = _pick_solver(time_limit_sec or settings.solver_time_limit_sec)
    status = handles.prob.solve(solver)

    label = STATUS_LABELS.get(status, "unknown")
    if label not in {"optimal"}:
        # 即使非最优也尝试读出可用部分；调用方根据 status 决定走诊断路径
        return Solution(status=label, objective=None, raw={"pulp_status": status})

    obj = pulp.value(handles.prob.objective) or 0.0

    actions: list[PlanAction] = []
    for (iid, t, d), var in handles.x.items():
        v = var.value() or 0.0
        if v > 1e-3:
            inst = handles.invest_lookup[iid]
            actions.append(
                PlanAction(
                    week_t=t,
                    instrument_id=iid,
                    action="invest",
                    amount=Decimal(str(round(v, 2))),
                    tenor_weeks=d,
                    instrument_name=inst.name,
                    instrument_kind="invest",
                )
            )
    for (fid, t, d), var in handles.y.items():
        v = var.value() or 0.0
        if v > 1e-3:
            inst = handles.finance_lookup[fid]
            actions.append(
                PlanAction(
                    week_t=t,
                    instrument_id=fid,
                    action="draw",
                    amount=Decimal(str(round(v, 2))),
                    tenor_weeks=d,
                    instrument_name=inst.name,
                    instrument_kind="finance",
                )
            )
    actions.sort(key=lambda a: (a.week_t, a.action, a.instrument_id))

    balance_curve = [
        Decimal(str(round(handles.B[t].value() or 0.0, 2)))
        for t in range(1, handles.horizon + 1)
    ]

    slack_curve: list[Decimal] = []
    if handles.slack:
        slack_curve = [
            Decimal(str(round(handles.slack[t].value() or 0.0, 2)))
            for t in range(1, handles.horizon + 1)
        ]

    # 融资依赖度：总动用 / 已知授信上限
    total_drawn = sum(
        (var.value() or 0.0)
        for (fid, _t, _d), var in handles.y.items()
    )
    total_available = sum(
        float(
            (inst := handles.finance_lookup[fid])
            and 1  # placeholder
        )
        for fid in handles.finance_lookup
    )
    # 实际可用授信：由调用方在持久化层提供，这里仅给原始动用值
    finance_dep_ratio = 0.0  # 由 multi_plan 层填，因为需要 credit_lines 上下文

    return Solution(
        status=label,
        objective=Decimal(str(round(obj, 2))),
        actions=actions,
        balance_curve=balance_curve,
        slack_curve=slack_curve,
        finance_dep_ratio=finance_dep_ratio,
        raw={"pulp_status": status, "total_drawn": total_drawn},
    )
