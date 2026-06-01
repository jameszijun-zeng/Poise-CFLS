"""多方案 + 不可行诊断 编排层。

输入：forecast（中性 net CF） + 主数据
输出：StrategyPlan × 3（稳健 / 折中 / 进取），或返回带缺口诊断的诊断方案
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from poise.domain.models import CreditLine, Forecast, Instrument
from poise.optimization.model import (
    RISK_MIN_CASH_MULT,
    Refinements,
    RiskKnob,
    build_model,
)


# 按 risk_knob 预设的精修档位（系统设计 §3.5）
# - 稳健：严集中度 + 高活钱底 + 重期限惩罚
# - 折中：中等
# - 进取：仅集中度防极端，其它放开
_REFINEMENTS_BY_KNOB: dict[RiskKnob, Refinements] = {
    "conservative": Refinements(
        concentration_cap=Decimal("0.30"),
        cash_tier_floor=Decimal("0.30"),
        tenor_mismatch_penalty=0.0005,
    ),
    "balanced": Refinements(
        concentration_cap=Decimal("0.40"),
        cash_tier_floor=Decimal("0.20"),
        tenor_mismatch_penalty=0.0001,
    ),
    "aggressive": Refinements(
        concentration_cap=Decimal("0.60"),
        cash_tier_floor=None,
        tenor_mismatch_penalty=0.0,
    ),
}
from poise.optimization.solver import PlanAction, Solution, solve


@dataclass
class PlanCandidate:
    risk_knob: RiskKnob
    solution: Solution
    expected_net_income: Decimal | None
    gap_warning_weeks: list[int]
    high_finance_dep: bool
    finance_dep_ratio: float
    safety_cushion_curve: list[Decimal]
    summary: str


@dataclass
class MultiPlanResult:
    candidates: list[PlanCandidate] = field(default_factory=list)
    infeasibility: dict | None = None  # 当任一档不可行时填，含松弛诊断


def _build_inputs_from_forecast(forecast: Forecast) -> tuple[list[Decimal], list[Decimal], Decimal]:
    """从 Forecast.payload 中抽出 (net_cf_neutral, min_cash, initial_balance)。"""
    p = forecast.payload or {}
    neutral = p.get("scenarios", {}).get("neutral", {})
    net_cf = [Decimal(v) for v in neutral.get("net_cf", [])]
    min_cash = [Decimal(v) for v in p.get("min_cash", [])]
    initial = Decimal(p.get("initial_balance", "0"))
    return net_cf, min_cash, initial


def _compute_finance_dep_ratio(actions: list[PlanAction], credit_lines: list[CreditLine]) -> float:
    """总融资动用金额 / 总可用授信上限。"""
    total_drawn = sum(
        (a.amount for a in actions if a.action == "draw"),
        Decimal(0),
    )
    total_avail = sum(
        ((cl.limit_amount or Decimal(0)) - (cl.used_amount or Decimal(0)) for cl in credit_lines),
        Decimal(0),
    )
    if total_avail <= 0:
        return 0.0
    return float(total_drawn / total_avail)


def _solve_one(
    forecast: Forecast,
    instruments: list[Instrument],
    credit_lines: list[CreditLine],
    risk_knob: RiskKnob,
    locks: dict[int, Decimal] | None,
) -> PlanCandidate | dict:
    """求解单档；返回 PlanCandidate 或不可行诊断 dict。"""
    net_cf, min_cash, b0 = _build_inputs_from_forecast(forecast)
    refinements = _REFINEMENTS_BY_KNOB.get(risk_knob)
    handles = build_model(
        forecast_net_cf=net_cf,
        initial_balance=b0,
        min_cash=min_cash,
        instruments=instruments,
        credit_lines=credit_lines,
        horizon=forecast.horizon_weeks,
        risk_knob=risk_knob,
        locks=locks,
        with_slack=False,
        refinements=refinements,
    )
    sol = solve(handles)

    if sol.status != "optimal":
        # 诊断路径不施加精修约束（避免与可行性条件叠加误判）
        diag = build_model(
            forecast_net_cf=net_cf,
            initial_balance=b0,
            min_cash=min_cash,
            instruments=instruments,
            credit_lines=credit_lines,
            horizon=forecast.horizon_weeks,
            risk_knob=risk_knob,
            locks=locks,
            with_slack=True,
        )
        diag_sol = solve(diag)
        return {
            "risk_knob": risk_knob,
            "status": sol.status,
            "diagnosis_status": diag_sol.status,
            "slack_weeks": [
                {"week_t": t + 1, "slack": str(diag_sol.slack_curve[t])}
                for t in range(len(diag_sol.slack_curve))
                if diag_sol.slack_curve[t] > 0
            ],
            "diag_objective": str(diag_sol.objective) if diag_sol.objective else None,
        }

    # 安全垫曲线（基于 risk_knob 的 MinCash 乘子）
    risk_mult = RISK_MIN_CASH_MULT[risk_knob]
    safety = [
        sol.balance_curve[t - 1] - (min_cash[t - 1] * Decimal(str(risk_mult)))
        for t in range(1, forecast.horizon_weeks + 1)
    ]
    gap_weeks = [t for t, c in enumerate(safety, start=1) if c < 0]
    dep_ratio = _compute_finance_dep_ratio(sol.actions, credit_lines)

    high_dep = dep_ratio > 0.5  # 系统设计 §3.7 dep_threshold 默认 50%

    summary = _make_summary(risk_knob, sol, gap_weeks, dep_ratio)

    return PlanCandidate(
        risk_knob=risk_knob,
        solution=sol,
        expected_net_income=sol.objective,
        gap_warning_weeks=gap_weeks,
        high_finance_dep=high_dep,
        finance_dep_ratio=dep_ratio,
        safety_cushion_curve=safety,
        summary=summary,
    )


def _make_summary(risk_knob: RiskKnob, sol: Solution, gaps: list[int], dep: float) -> str:
    invest_actions = sum(1 for a in sol.actions if a.action == "invest")
    finance_actions = sum(1 for a in sol.actions if a.action == "draw")
    invest_total = sum((a.amount for a in sol.actions if a.action == "invest"), Decimal(0))
    finance_total = sum((a.amount for a in sol.actions if a.action == "draw"), Decimal(0))
    label = {"conservative": "稳健", "balanced": "折中", "aggressive": "进取"}[risk_knob]
    parts = [
        f"档位：{label}",
        f"预期净收益 ¥{sol.objective:,.0f}",
        f"投资动作 {invest_actions} 笔（总 ¥{invest_total:,.0f}）",
        f"融资动作 {finance_actions} 笔（总 ¥{finance_total:,.0f}）",
        f"融资依赖度 {dep:.1%}",
    ]
    if gaps:
        parts.append(f"缺口周 W{','.join(map(str, gaps))}")
    return " · ".join(parts)


def generate_plans(
    forecast: Forecast,
    instruments: list[Instrument],
    credit_lines: list[CreditLine],
    *,
    risk_knobs: tuple[RiskKnob, ...] = ("conservative", "balanced", "aggressive"),
    locks: dict[int, Decimal] | None = None,
) -> MultiPlanResult:
    """对三个 risk_knob 各求解一次，组装 MultiPlanResult。

    若某档不可行，对该档运行松弛诊断并归集到 infeasibility 字段；
    其它档若可行仍正常返回，让用户看到至少一套可执行方案。
    """
    result = MultiPlanResult()
    diagnoses: list[dict] = []

    for knob in risk_knobs:
        out = _solve_one(forecast, instruments, credit_lines, knob, locks)
        if isinstance(out, dict):
            diagnoses.append(out)
        else:
            result.candidates.append(out)

    if diagnoses:
        result.infeasibility = {"diagnoses": diagnoses}

    return result
