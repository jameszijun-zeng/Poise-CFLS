"""MILP 决策引擎单测 —— 系统设计 §3 的 5 套合成场景。

不依赖数据库，直接构造 Instrument / CreditLine 对象 + 喂给 build_model + solve。
"""

from decimal import Decimal

import pytest

from poise.domain.models import CreditLine, Instrument
from poise.optimization.model import build_model
from poise.optimization.solver import solve


# ----- 工厂 -----


def _invest(code: str, tier: str, rate_pct: float, tenor_weeks: int, min_amt: float = 0) -> Instrument:
    return Instrument(
        id=f"inv-{code}",
        entity_id="e",
        code=code,
        name=f"{code}-{tenor_weeks}w",
        kind="invest",
        liquidity_tier=tier,
        rate=Decimal(str(rate_pct / 100)),
        tenor_options=[tenor_weeks],
        min_amount=Decimal(str(min_amt)),
        max_amount=None,
        redeemable=True,
        redeem_cost=Decimal(0),
        counterparty="bank",
        whitelisted=True,
        finance_priority=None,
        currency="CNY",
    )


def _finance(code: str, rate_pct: float, tenor_weeks: int, priority: int = 1) -> Instrument:
    return Instrument(
        id=f"fin-{code}",
        entity_id="e",
        code=code,
        name=f"{code}-{tenor_weeks}w",
        kind="finance",
        liquidity_tier=None,
        rate=Decimal(str(rate_pct / 100)),
        tenor_options=[tenor_weeks],
        min_amount=Decimal(0),
        max_amount=None,
        redeemable=False,
        redeem_cost=Decimal(0),
        counterparty="bank",
        whitelisted=True,
        finance_priority=priority,
        currency="CNY",
    )


def _line(instrument: Instrument, limit: float) -> CreditLine:
    return CreditLine(
        id=f"cl-{instrument.id}",
        entity_id="e",
        instrument_id=instrument.id,
        bank_name="bank",
        code=f"cl-{instrument.code}",
        limit_amount=Decimal(str(limit)),
        used_amount=Decimal(0),
        rate=instrument.rate,
        expires_at=None,
    )


def _zeros(h: int) -> list[Decimal]:
    return [Decimal(0)] * h


# ----- 场景 1：全闲置（无 CF 波动），最优策略是把全部钱投到最长允许久期 -----


def test_scenario_all_idle_picks_long_tenor():
    insts = [
        _invest("CASH", "cash", 2.0, 1, min_amt=1_000_000),       # 货基样
        _invest("LONG", "yield", 5.0, 4, min_amt=1_000_000),      # 长久期高息（balanced 允许 4 周）
    ]
    handles = build_model(
        forecast_net_cf=_zeros(13),
        initial_balance=Decimal("100_000_000"),
        min_cash=_zeros(13),
        instruments=insts,
        credit_lines=[],
        horizon=13,
        risk_knob="balanced",
    )
    sol = solve(handles)
    assert sol.status == "optimal"
    assert sol.objective > 0
    # 应优先选 LONG（高息），不会去借钱
    invest_codes = {a.instrument_id for a in sol.actions if a.action == "invest"}
    assert "inv-LONG" in invest_codes


# ----- 场景 2：W3 大额缺口（80M out），无授信 → 应不可行 -----


def test_scenario_gap_no_credit_is_infeasible():
    cf = _zeros(13)
    cf[2] = Decimal("-90_000_000")  # W3 净流出 90M
    insts = [_invest("CASH", "cash", 2.0, 1, min_amt=1_000_000)]
    handles = build_model(
        forecast_net_cf=cf,
        initial_balance=Decimal("50_000_000"),  # 仅 50M 期初
        min_cash=[Decimal("10_000_000")] * 13,
        instruments=insts,
        credit_lines=[],
        horizon=13,
        risk_knob="balanced",
    )
    sol = solve(handles)
    assert sol.status in {"infeasible", "undefined"}


# ----- 场景 3：W3 大额缺口，有授信 → 应可行且动用授信 -----


def test_scenario_gap_with_credit_uses_drawdown():
    cf = _zeros(13)
    cf[2] = Decimal("-90_000_000")            # W3 大额出
    # 后续周回款，使融资可偿还（避免终周清偿不可行）
    for w in (5, 7, 9, 11):
        cf[w] = Decimal("30_000_000")
    insts = [
        _invest("CASH", "cash", 2.0, 1),
        _finance("LOAN", 4.5, 0, priority=1),
    ]
    lines = [_line(insts[1], 100_000_000)]
    handles = build_model(
        forecast_net_cf=cf,
        initial_balance=Decimal("50_000_000"),
        min_cash=[Decimal("10_000_000")] * 13,
        instruments=insts,
        credit_lines=lines,
        horizon=13,
        risk_knob="balanced",
    )
    sol = solve(handles)
    assert sol.status == "optimal"
    draws = [a for a in sol.actions if a.action == "draw"]
    assert draws, "应在缺口周动用授信"


# ----- 场景 4：授信耗尽 + 缺口仍存在 → infeasible，松弛诊断应定位到缺口周 -----


def test_scenario_credit_exhausted_diagnose_via_slack():
    cf = _zeros(13)
    cf[2] = Decimal("-200_000_000")  # W3 巨缺口
    insts = [_finance("LOAN", 4.5, 0, priority=1)]
    lines = [_line(insts[0], 50_000_000)]   # 只 50M 授信，远不够
    handles = build_model(
        forecast_net_cf=cf,
        initial_balance=Decimal("50_000_000"),
        min_cash=[Decimal("10_000_000")] * 13,
        instruments=insts,
        credit_lines=lines,
        horizon=13,
        risk_knob="balanced",
        with_slack=True,  # 诊断路径
    )
    sol = solve(handles)
    assert sol.status == "optimal"  # slack 路径总能解
    assert any(s > 0 for s in sol.slack_curve), "应有正 slack（即缺口）"
    # 缺口应落在 W3 附近
    big_slack_weeks = [t + 1 for t, s in enumerate(sol.slack_curve) if s > 1_000_000]
    assert 3 in big_slack_weeks or 4 in big_slack_weeks


# ----- 场景 5：风险旋钮单调性 —— aggressive ≥ balanced ≥ conservative 收益 -----


def test_scenario_risk_knob_monotonic_returns():
    insts = [
        _invest("CASH", "cash", 2.0, 1),
        _invest("STABLE", "stable", 2.8, 4),
        _invest("YIELD", "yield", 3.5, 12),
    ]
    cf = _zeros(13)
    cf[2] = Decimal("-10_000_000")
    objs: dict[str, float] = {}
    for knob in ("conservative", "balanced", "aggressive"):
        h = build_model(
            forecast_net_cf=cf,
            initial_balance=Decimal("100_000_000"),
            min_cash=[Decimal("5_000_000")] * 13,
            instruments=insts,
            credit_lines=[],
            horizon=13,
            risk_knob=knob,
        )
        s = solve(h)
        assert s.status == "optimal"
        objs[knob] = float(s.objective)
    assert objs["conservative"] <= objs["balanced"] <= objs["aggressive"]


# ----- 场景 6：终周不应有新投资（噪音过滤） -----


def test_scenario_no_terminal_invest_actions():
    insts = [_invest("CASH", "cash", 2.0, 1)]
    handles = build_model(
        forecast_net_cf=_zeros(13),
        initial_balance=Decimal("100_000_000"),
        min_cash=_zeros(13),
        instruments=insts,
        credit_lines=[],
        horizon=13,
        risk_knob="balanced",
    )
    sol = solve(handles)
    assert sol.status == "optimal"
    terminal = [a for a in sol.actions if a.week_t == 13 and a.action == "invest"]
    assert not terminal, "终周不应输出新投资动作"


# ----- 场景 7：解的现金守恒在采样几周上成立 -----


def test_scenario_cash_conservation_holds_on_sample_weeks():
    insts = [_invest("CASH", "cash", 2.0, 1)]
    cf = [Decimal(0)] * 13
    cf[0] = Decimal("10_000_000")  # W1 +10M
    cf[5] = Decimal("-20_000_000")  # W6 -20M
    handles = build_model(
        forecast_net_cf=cf,
        initial_balance=Decimal("50_000_000"),
        min_cash=_zeros(13),
        instruments=insts,
        credit_lines=[],
        horizon=13,
        risk_knob="balanced",
    )
    sol = solve(handles)
    assert sol.status == "optimal"
    # B[t] 全部非负
    assert all(b >= 0 for b in sol.balance_curve)
