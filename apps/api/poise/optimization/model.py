"""多期现金调度 MILP 模型构造器。

对应系统设计 §3：在 13 周时间轴上排布投/融/留，使全周期净财务收益最大，
且每周满足流动性安全与各项额度约束。

设计要点：
- 决策变量：x[i,t,d] 投资 / y[f,t,d] 融资 / red[i,t,d_orig] 提前赎回 /
  B[t] 周末余额 / z[i,t,d] 最小起投触发的整数变量
- 现金守恒（核心约束 C0）：每周余额 = 上周 + 净 CF + 投资到期回流 +
  新增融资 − 新投出 − 融资到期偿还 + 赎回回流
- 利率：年化 → 周化 = annual / 52；存续 d 周累计利息 = rate_weekly · d
- tenor=0（T+0）建模为 1 周最小占用（避免周内多次进出复杂度）
- 融资 tenor=0（流贷"随借随还"）建模为"借至 horizon 末"，成本按持有周数累加
- 投资到期 / 融资到期 若超出 horizon：现金不在 horizon 内回流，但收益/成本
  仍计入目标（半个周期外的"已锁"敞口）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

# ---- C7-C9 精修约束的默认参数（系统设计 §3.5） ----
# 这些可被 build_model 的 refinements 参数覆盖
DEFAULT_CONCENTRATION_CAP = Decimal("0.40")   # 单对手方 ≤ 40% 总投资
DEFAULT_CASH_TIER_FLOOR = Decimal("0.20")     # 活钱层 ≥ 20% 总投资
DEFAULT_TENOR_MISMATCH_PENALTY = 0.0001        # 长久期占用的目标惩罚权重（按周加权）

from pulp import LpBinary, LpContinuous, LpMaximize, LpMinimize, LpProblem, LpVariable, lpSum

from poise.domain.models import CreditLine, Instrument

RiskKnob = Literal["conservative", "balanced", "aggressive"]

# riskKnob 三档对应的 MinCash 乘子（系统设计 §3.6）
RISK_MIN_CASH_MULT: dict[RiskKnob, float] = {
    "conservative": 1.20,
    "balanced": 1.00,
    "aggressive": 0.85,
}

# riskKnob 对久期上限（周）
RISK_MAX_TENOR: dict[RiskKnob, int] = {
    "conservative": 4,
    "balanced": 12,
    "aggressive": 26,
}

WEEKS_PER_YEAR = Decimal(52)


@dataclass
class ModelHandles:
    """暴露给 solver/persist 的所有 LP 句柄与元数据。"""

    prob: LpProblem
    x: dict[tuple[str, int, int], LpVariable]
    y: dict[tuple[str, int, int], LpVariable]
    B: dict[int, LpVariable]
    z: dict[tuple[str, int, int], LpVariable]
    slack: dict[int, LpVariable] = field(default_factory=dict)

    invest_options: list[tuple[str, int]] = field(default_factory=list)
    finance_options: list[tuple[str, int]] = field(default_factory=list)
    invest_lookup: dict[str, Instrument] = field(default_factory=dict)
    finance_lookup: dict[str, Instrument] = field(default_factory=dict)
    rate_map: dict[str, float] = field(default_factory=dict)
    horizon: int = 13
    risk_knob: RiskKnob = "balanced"


def _norm_tenor(d: int, horizon: int, is_finance: bool) -> int:
    """tenor=0 的归一化：投资视为 1 周（T+0 近似），融资视为持至 horizon 末。"""
    if d > 0:
        return d
    return horizon if is_finance else 1


@dataclass
class Refinements:
    """C7-C9 精修约束（系统设计 §3.5）。

    - concentration_cap: 单对手方持仓 ≤ ρ × 总投资（None=关闭 C7）
    - cash_tier_floor:   活钱层持仓 ≥ λ × 总投资  （None=关闭 C8）
    - tenor_mismatch_penalty: 长久期占用的目标惩罚权重（0=关闭 C9）
    """

    concentration_cap: Decimal | None = None
    cash_tier_floor: Decimal | None = None
    tenor_mismatch_penalty: float = 0.0


def build_model(
    *,
    forecast_net_cf: list[Decimal],     # [CF[1], CF[2], ..., CF[H]]，长度 = horizon
    initial_balance: Decimal,
    min_cash: list[Decimal],            # MinCash[1..H]
    instruments: list[Instrument],
    credit_lines: list[CreditLine],
    horizon: int = 13,
    risk_knob: RiskKnob = "balanced",
    locks: dict[int, Decimal] | None = None,
    with_slack: bool = False,
    refinements: Refinements | None = None,
) -> ModelHandles:
    """构造 MILP。

    参数：
      forecast_net_cf: 长度 = horizon 的净现金流（来自预测引擎中性情景）
      initial_balance: 期初可用现金
      min_cash: MinCash[t]，长度 = horizon
      instruments: 全部品种（含投资 + 融资），仅 whitelisted 进入
      credit_lines: 授信额度（按 instrument_id 关联）
      locks: 资金锁定（在 MinCash 之上额外保留），{week_t: amount}
      with_slack: True 则为每周 B[t] 加松弛变量 slack[t]≥0，目标改为
                  最小化 Σ slack[t]（不可行诊断路径，§3.8）

    返回：ModelHandles，含 prob、各变量字典与元数据。
    """

    assert len(forecast_net_cf) == horizon, "forecast_net_cf 长度必须等于 horizon"
    assert len(min_cash) == horizon, "min_cash 长度必须等于 horizon"
    locks = locks or {}

    invest_insts = [i for i in instruments if i.kind == "invest" and i.whitelisted]
    finance_insts = [i for i in instruments if i.kind == "finance" and i.whitelisted]
    invest_lookup = {i.id: i for i in invest_insts}
    finance_lookup = {i.id: i for i in finance_insts}

    # 周化利率
    rate_map: dict[str, float] = {}
    for i in invest_insts + finance_insts:
        rate_map[i.id] = float(Decimal(str(i.rate)) / WEEKS_PER_YEAR)

    # (instrument_id, normalized_tenor)
    invest_options: list[tuple[str, int]] = []
    for i in invest_insts:
        for d_raw in (i.tenor_options or [0]):
            d = _norm_tenor(int(d_raw), horizon, is_finance=False)
            if (i.id, d) not in invest_options:
                invest_options.append((i.id, d))
    finance_options: list[tuple[str, int]] = []
    for f in finance_insts:
        for d_raw in (f.tenor_options or [0]):
            d = _norm_tenor(int(d_raw), horizon, is_finance=True)
            if (f.id, d) not in finance_options:
                finance_options.append((f.id, d))

    # 久期上限（按 risk_knob 过滤过长久期）
    max_tenor = RISK_MAX_TENOR[risk_knob]
    invest_options = [(i, d) for (i, d) in invest_options if d <= max_tenor]

    sense = LpMinimize if with_slack else LpMaximize
    prob = LpProblem(f"poise_{risk_knob}{'_diag' if with_slack else ''}", sense)

    # ===== 决策变量 =====
    x = {
        (i, t, d): LpVariable(f"x_{i[:6]}_{t}_{d}", lowBound=0, cat=LpContinuous)
        for (i, d) in invest_options
        for t in range(1, horizon + 1)
    }
    y = {
        (f, t, d): LpVariable(f"y_{f[:6]}_{t}_{d}", lowBound=0, cat=LpContinuous)
        for (f, d) in finance_options
        for t in range(1, horizon + 1)
    }
    z = {
        (i, t, d): LpVariable(f"z_{i[:6]}_{t}_{d}", cat=LpBinary)
        for (i, d) in invest_options
        for t in range(1, horizon + 1)
    }
    # 诊断模式下放开 B[t] 下界（用一个很大的负值而非 None，避免 CBC 数值上判 unbounded）
    # 让 slack 真正吸收"绝对没钱"的缺口；否则 B[t]≥0 的硬约束会让真实缺口场景直接 infeasible
    # 而拿不到诊断。
    if with_slack:
        b_lower: float | None = -1e15
    else:
        b_lower = 0
    B = {t: LpVariable(f"B_{t}", lowBound=b_lower, cat=LpContinuous) for t in range(0, horizon + 1)}

    slack: dict[int, LpVariable] = {}
    if with_slack:
        slack = {t: LpVariable(f"slack_{t}", lowBound=0, cat=LpContinuous) for t in range(1, horizon + 1)}

    # ===== 期初余额 =====
    prob += B[0] == float(initial_balance), "init_balance"

    # ===== 现金守恒（C0）∀ t =====
    # 终周（t=H）额外强制：
    #   1. 未到期融资在 H 全额清偿（本+按有效持有周计息）——杜绝"借不用还"套利
    #   2. 未到期投资按"已锁未还"处理：本金不在 horizon 内回流，但终值仍计入 B[H]，
    #      避免被模型当作"沉没"，理论上等同对冲了第 1 点的极端情形。
    risk_mult = RISK_MIN_CASH_MULT[risk_knob]
    for t in range(1, horizon + 1):
        cf_t = float(forecast_net_cf[t - 1])

        invest_matur = lpSum(
            x[(i, t - d, d)] * (1.0 + rate_map[i] * d)
            for (i, d) in invest_options
            if t - d >= 1
        )
        new_invest = lpSum(x[(i, t, d)] for (i, d) in invest_options)
        new_finance = lpSum(y[(f, t, d)] for (f, d) in finance_options)
        finance_matur = lpSum(
            y[(f, t - d, d)] * (1.0 + rate_map[f] * d)
            for (f, d) in finance_options
            if t - d >= 1
        )

        if t == horizon:
            # 终周强制清偿未到期融资（按"已持有周数"计利）
            terminal_finance_repay = lpSum(
                y[(f, t_b, d)] * (1.0 + rate_map[f] * (horizon - t_b + 1))
                for (f, d) in finance_options
                for t_b in range(1, horizon + 1)
                if t_b + d > horizon
            )
            # 终周回收未到期投资本金（按"已持有周数"计利的终值）
            terminal_invest_value = lpSum(
                x[(i, t_b, d)] * (1.0 + rate_map[i] * (horizon - t_b + 1))
                for (i, d) in invest_options
                for t_b in range(1, horizon + 1)
                if t_b + d > horizon
            )
            prob += (
                B[t] == B[t - 1] + cf_t + invest_matur + new_finance - new_invest
                       - finance_matur - terminal_finance_repay + terminal_invest_value,
                f"cash_conserv_{t}",
            )
        else:
            prob += (
                B[t] == B[t - 1] + cf_t + invest_matur + new_finance - new_invest - finance_matur,
                f"cash_conserv_{t}",
            )

    # ===== C1 流动性安全（with_slack 时引入 slack） =====
    for t in range(1, horizon + 1):
        rhs = float(min_cash[t - 1]) * risk_mult + float(locks.get(t, Decimal(0)))
        if with_slack:
            prob += B[t] + slack[t] >= rhs, f"liquidity_{t}"
        else:
            prob += B[t] >= rhs, f"liquidity_{t}"

    # ===== C2 授信额度（按 instrument 维度汇总） =====
    line_by_inst: dict[str, Decimal] = {}
    for cl in credit_lines:
        if cl.instrument_id:
            avail = (cl.limit_amount or Decimal(0)) - (cl.used_amount or Decimal(0))
            line_by_inst[cl.instrument_id] = line_by_inst.get(cl.instrument_id, Decimal(0)) + avail
    for f in finance_insts:
        cap = line_by_inst.get(f.id)
        if cap is None:
            continue
        tenors_for_f = [d for (fid, d) in finance_options if fid == f.id]
        prob += (
            lpSum(y[(f.id, t, d)] for t in range(1, horizon + 1) for d in tenors_for_f) <= float(cap),
            f"credit_limit_{f.id[:6]}",
        )

    # ===== C5 起投/上限（触发整数 z） =====
    # big-M 上限：用 initial_balance + Σ正净 CF 作为绝对上界，避免 1e15 导致 LP 松弛过松、
    # branch-and-bound 收敛慢。
    abs_cap = float(initial_balance) + sum(float(v) for v in forecast_net_cf if v > 0)
    for (i, d) in invest_options:
        inst = invest_lookup[i]
        min_amt = float(inst.min_amount or 0)
        max_amt = float(inst.max_amount) if inst.max_amount else abs_cap
        for t in range(1, horizon + 1):
            if min_amt > 0:
                prob += x[(i, t, d)] >= min_amt * z[(i, t, d)], f"minamt_{i[:6]}_{t}_{d}"
            prob += x[(i, t, d)] <= max_amt * z[(i, t, d)], f"maxamt_{i[:6]}_{t}_{d}"

    # 禁止终周新投资（t=H 时投出立刻被终值回收，等同闲置且产生噪音动作）
    for (i, d) in invest_options:
        prob += x[(i, horizon, d)] == 0, f"no_terminal_invest_{i[:6]}_{d}"
        prob += z[(i, horizon, d)] == 0, f"no_terminal_z_{i[:6]}_{d}"

    # ===== C7-C9 精修约束（§3.5） =====
    ref = refinements or Refinements()

    # 总投资本金（同一笔多周可重复计数，作为分母）
    total_invest_principal = lpSum(
        x[(i, t, d)] for (i, d) in invest_options for t in range(1, horizon + 1)
    )

    # C7 集中度：单对手方持仓 ≤ ρ × 总投资
    if ref.concentration_cap is not None:
        # 按 counterparty 分组
        cp_to_keys: dict[str, list[tuple[str, int]]] = {}
        for (i, d) in invest_options:
            cp = invest_lookup[i].counterparty or "_unknown"
            cp_to_keys.setdefault(cp, []).append((i, d))
        cap = float(ref.concentration_cap)
        for cp, keys in cp_to_keys.items():
            cp_invest = lpSum(
                x[(i, t, d)] for (i, d) in keys for t in range(1, horizon + 1)
            )
            prob += (
                cp_invest <= cap * total_invest_principal,
                f"concentration_{cp[:8]}",
            )

    # C8 流动性分层：活钱层持仓 ≥ λ × 总投资
    if ref.cash_tier_floor is not None:
        cash_keys = [(i, d) for (i, d) in invest_options if invest_lookup[i].liquidity_tier == "cash"]
        if cash_keys:
            floor = float(ref.cash_tier_floor)
            cash_invest = lpSum(
                x[(i, t, d)] for (i, d) in cash_keys for t in range(1, horizon + 1)
            )
            prob += (
                cash_invest >= floor * total_invest_principal,
                "liquidity_tier_floor",
            )

    # ===== 目标 =====
    # 利息/成本一律按"有效持有周数 = min(d, horizon - t + 1)"计算，与现金守恒终周
    # 强制清偿/回收的口径一致：
    interest_rev = lpSum(
        x[(i, t, d)] * rate_map[i] * min(d, horizon - t + 1)
        for (i, d) in invest_options
        for t in range(1, horizon + 1)
    )
    finance_cost = lpSum(
        y[(f, t, d)] * rate_map[f] * min(d, horizon - t + 1)
        for (f, d) in finance_options
        for t in range(1, horizon + 1)
    )

    # C9 期限错配惩罚：对长久期占用按 d² 加权（鼓励短久期、避免被锁太久）
    tenor_penalty = 0
    if ref.tenor_mismatch_penalty > 0:
        tenor_penalty = lpSum(
            x[(i, t, d)] * (d * d) * ref.tenor_mismatch_penalty * rate_map[i]
            for (i, d) in invest_options
            for t in range(1, horizon + 1)
        )

    if with_slack:
        # 不可行诊断路径：纯粹最小化 Σ slack[t]（构造时已 LpMinimize）。
        # 目标是定位缺口位置与规模，不再附带 tie-break 项。
        prob += lpSum(slack[t] for t in range(1, horizon + 1))
    else:
        prob += interest_rev - finance_cost - tenor_penalty

    return ModelHandles(
        prob=prob,
        x=x, y=y, B=B, z=z, slack=slack,
        invest_options=invest_options,
        finance_options=finance_options,
        invest_lookup=invest_lookup,
        finance_lookup=finance_lookup,
        rate_map=rate_map,
        horizon=horizon,
        risk_knob=risk_knob,
    )
