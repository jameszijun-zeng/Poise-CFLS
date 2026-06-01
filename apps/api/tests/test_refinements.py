"""C7-C9 精修约束单测（系统设计 §3.5 软约束）。

- C7 集中度上限：单对手方持仓 ≤ ρ × 总投资
- C8 流动性分层底：活钱层持仓 ≥ λ × 总投资
- C9 期限错配惩罚：长久期占用在目标中被扣分
"""

from decimal import Decimal

from poise.domain.models import CreditLine, Instrument
from poise.optimization.model import Refinements, build_model
from poise.optimization.solver import solve


def _invest(code: str, tier: str, rate_pct: float, tenor_weeks: int, cp: str = "bankA") -> Instrument:
    return Instrument(
        id=f"inv-{code}", entity_id="e", code=code, name=code,
        kind="invest", liquidity_tier=tier,
        rate=Decimal(str(rate_pct / 100)), tenor_options=[tenor_weeks],
        min_amount=Decimal(0), max_amount=None,
        redeemable=True, redeem_cost=Decimal(0),
        counterparty=cp, whitelisted=True, finance_priority=None, currency="CNY",
    )


def _zeros(n: int) -> list[Decimal]:
    return [Decimal(0)] * n


def test_c7_concentration_caps_single_counterparty():
    """C7：高息但同一对手方的品种持仓应被压到 ≤ ρ × 总投资。"""
    insts = [
        _invest("HIGH_A", "yield", 6.0, 4, cp="bankA"),    # 最高息
        _invest("LOW_B",  "yield", 2.0, 4, cp="bankB"),    # 低息
    ]
    handles = build_model(
        forecast_net_cf=_zeros(13),
        initial_balance=Decimal("100_000_000"),
        min_cash=_zeros(13),
        instruments=insts,
        credit_lines=[],
        horizon=13,
        risk_knob="balanced",
        refinements=Refinements(concentration_cap=Decimal("0.4")),
    )
    sol = solve(handles)
    assert sol.status == "optimal"
    total_invest = sum((a.amount for a in sol.actions if a.action == "invest"), Decimal(0))
    bank_a_invest = sum(
        (a.amount for a in sol.actions if a.action == "invest" and a.instrument_id == "inv-HIGH_A"),
        Decimal(0),
    )
    # 同行不得超 40% × 总
    assert bank_a_invest <= total_invest * Decimal("0.40") + Decimal(1)  # 数值容差


def test_c7_without_constraint_concentrates_all_to_best():
    """对照：关闭 C7 时应该全压最高息品种。"""
    insts = [
        _invest("HIGH_A", "yield", 6.0, 4, cp="bankA"),
        _invest("LOW_B", "yield", 2.0, 4, cp="bankB"),
    ]
    handles = build_model(
        forecast_net_cf=_zeros(13),
        initial_balance=Decimal("100_000_000"),
        min_cash=_zeros(13),
        instruments=insts,
        credit_lines=[],
        horizon=13,
        risk_knob="balanced",
        refinements=None,
    )
    sol = solve(handles)
    assert sol.status == "optimal"
    bank_a_invest = sum(
        (a.amount for a in sol.actions if a.action == "invest" and a.instrument_id == "inv-HIGH_A"),
        Decimal(0),
    )
    bank_b_invest = sum(
        (a.amount for a in sol.actions if a.action == "invest" and a.instrument_id == "inv-LOW_B"),
        Decimal(0),
    )
    # 高息品种应该被显著重仓（≥ 低息）
    assert bank_a_invest >= bank_b_invest


def test_c8_cash_tier_floor():
    """C8：活钱层应至少占 λ × 总投资。"""
    insts = [
        _invest("MMF", "cash", 2.0, 1, cp="bankX"),         # 低息活钱
        _invest("TD",  "yield", 4.0, 4, cp="bankY"),        # 高息锁定
    ]
    handles = build_model(
        forecast_net_cf=_zeros(13),
        initial_balance=Decimal("100_000_000"),
        min_cash=_zeros(13),
        instruments=insts,
        credit_lines=[],
        horizon=13,
        risk_knob="balanced",
        refinements=Refinements(cash_tier_floor=Decimal("0.25")),
    )
    sol = solve(handles)
    assert sol.status == "optimal"
    total_invest = sum((a.amount for a in sol.actions if a.action == "invest"), Decimal(0))
    cash_invest = sum(
        (a.amount for a in sol.actions if a.action == "invest" and a.instrument_id == "inv-MMF"),
        Decimal(0),
    )
    # 活钱层 ≥ 25% 总投资（数值容差）
    assert cash_invest >= total_invest * Decimal("0.25") - Decimal(1)


def test_c9_tenor_penalty_shifts_to_shorter_tenor():
    """C9：开启期限错配惩罚后，等利率下应偏好短久期。"""
    # 两个等"周化收益率 × 期"的品种，但 d 长得多
    insts = [
        _invest("SHORT", "stable", 2.0, 1),    # d=1
        _invest("LONG",  "stable", 2.0, 12),   # d=12，惩罚因 d²=144
    ]
    handles_no_pen = build_model(
        forecast_net_cf=_zeros(13),
        initial_balance=Decimal("100_000_000"),
        min_cash=_zeros(13),
        instruments=insts,
        credit_lines=[],
        horizon=13,
        risk_knob="balanced",
        refinements=Refinements(tenor_mismatch_penalty=0.0),
    )
    sol_no = solve(handles_no_pen)

    handles_pen = build_model(
        forecast_net_cf=_zeros(13),
        initial_balance=Decimal("100_000_000"),
        min_cash=_zeros(13),
        instruments=insts,
        credit_lines=[],
        horizon=13,
        risk_knob="balanced",
        refinements=Refinements(tenor_mismatch_penalty=0.01),  # 强惩罚
    )
    sol_pen = solve(handles_pen)
    assert sol_no.status == sol_pen.status == "optimal"

    short_no = sum((a.amount for a in sol_no.actions if a.instrument_id == "inv-SHORT"), Decimal(0))
    long_no = sum((a.amount for a in sol_no.actions if a.instrument_id == "inv-LONG"), Decimal(0))
    short_pen = sum((a.amount for a in sol_pen.actions if a.instrument_id == "inv-SHORT"), Decimal(0))
    long_pen = sum((a.amount for a in sol_pen.actions if a.instrument_id == "inv-LONG"), Decimal(0))

    # 加重 C9 惩罚后，短久期份额应升高
    no_short_ratio = short_no / (short_no + long_no) if (short_no + long_no) > 0 else 0
    pen_short_ratio = short_pen / (short_pen + long_pen) if (short_pen + long_pen) > 0 else 0
    assert pen_short_ratio >= no_short_ratio


def test_refinements_disabled_by_default():
    """不传 refinements 时应等同于关闭所有 C7-C9。"""
    insts = [_invest("MMF", "cash", 2.0, 1)]
    handles = build_model(
        forecast_net_cf=_zeros(13),
        initial_balance=Decimal("100_000_000"),
        min_cash=_zeros(13),
        instruments=insts, credit_lines=[],
        horizon=13, risk_knob="balanced",
    )
    sol = solve(handles)
    assert sol.status == "optimal"
