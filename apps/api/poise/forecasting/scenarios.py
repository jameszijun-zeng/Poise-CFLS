"""中性 / 悲观情景变换。

设计原则（系统设计 §4.2）：
- neutral：分层聚合的期望值，直接作为优化求解的输入 CF[t]
- pessimistic：收入打折 / 支出从紧，用于安全压测与缺口预警

MVP 用可配置规则；未来可替换为概率模型（如蒙特卡洛 / 历史分位数）。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from poise.forecasting.layered import LAYERS, WeekLayered

ScenarioMode = Literal["neutral", "pessimistic"]


@dataclass
class PessimisticRules:
    """对各层的悲观乘子。"""

    # 确定层：合同/已知到期，悲观情景下也基本如约（但可能略有延后）
    deterministic_inflow_factor: Decimal = Decimal("0.95")
    deterministic_outflow_factor: Decimal = Decimal("1.00")
    # 规律层：基于历史的统计估算，悲观情景下波动更大
    pattern_inflow_factor: Decimal = Decimal("0.85")
    pattern_outflow_factor: Decimal = Decimal("1.05")
    # 不确定层：业务驱动，悲观情景下显著打折
    uncertain_inflow_factor: Decimal = Decimal("0.70")
    uncertain_outflow_factor: Decimal = Decimal("1.10")


DEFAULT_PESSIMISTIC = PessimisticRules()


def week_net(wk: WeekLayered, mode: ScenarioMode, rules: PessimisticRules | None = None) -> Decimal:
    """返回某情景下该周的净现金流。

    neutral：直接取期望值之和。
    pessimistic：按层施加 inflow/outflow 乘子后求净。
    """
    if mode == "neutral":
        return wk.net

    r = rules or DEFAULT_PESSIMISTIC
    factors = {
        "deterministic": (r.deterministic_inflow_factor, r.deterministic_outflow_factor),
        "pattern": (r.pattern_inflow_factor, r.pattern_outflow_factor),
        "uncertain": (r.uncertain_inflow_factor, r.uncertain_outflow_factor),
    }
    net = Decimal(0)
    for layer in LAYERS:
        cell = wk.by_layer[layer]
        fin, fout = factors[layer]
        net += cell.inflow * fin - cell.outflow * fout
    return net


def week_band(wk: WeekLayered, mode: ScenarioMode) -> tuple[Decimal | None, Decimal | None]:
    """uncertain 层 ±20% 转化的区间，仅对 uncertain 非零的周返回。"""
    u = wk.by_layer["uncertain"]
    if u.inflow == 0 and u.outflow == 0:
        return None, None
    # 区间在情景净值上下展开
    center = week_net(wk, mode)
    band_in = u.inflow * Decimal("0.20")
    band_out = u.outflow * Decimal("0.20")
    return center - band_in - band_out, center + band_in + band_out
