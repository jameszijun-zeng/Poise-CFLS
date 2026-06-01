from datetime import date
from decimal import Decimal

import pytest

from poise.domain.models import CashFlowItem, ReserveRule
from poise.forecasting.layered import LAYERS, aggregate_layered, serialize_layered
from poise.forecasting.reserve import RIGID_CATEGORIES, compute_min_cash
from poise.forecasting.scenarios import DEFAULT_PESSIMISTIC, week_band, week_net


def _cf(**kw):
    """构造一条 CashFlowItem，仅供单测使用（不入库）。"""
    defaults = dict(
        id="cf-x",
        entity_id="e-x",
        account_id=None,
        direction="inflow",
        category="sales_collection",
        source_type="ar",
        expected_date=date(2026, 6, 1),
        week_t=1,
        amount=Decimal("1000000.00"),
        currency="CNY",
        certainty_layer="deterministic",
        counterparty=None,
        notes=None,
    )
    defaults.update(kw)
    return CashFlowItem(**defaults)


def test_aggregate_layered_basic():
    items = [
        _cf(week_t=1, direction="inflow", amount=Decimal("10"), certainty_layer="deterministic"),
        _cf(week_t=1, direction="outflow", amount=Decimal("4"), certainty_layer="deterministic"),
        _cf(week_t=1, direction="inflow", amount=Decimal("5"), certainty_layer="uncertain"),
    ]
    by_week = aggregate_layered(items)
    assert 1 in by_week
    cell_det = by_week[1].by_layer["deterministic"]
    assert cell_det.inflow == Decimal("10")
    assert cell_det.outflow == Decimal("4")
    assert by_week[1].by_layer["uncertain"].inflow == Decimal("5")
    assert by_week[1].net == Decimal("11")  # 10 - 4 + 5


def test_aggregate_layered_skips_out_of_range_weeks():
    items = [_cf(week_t=14, amount=Decimal("10"))]
    assert aggregate_layered(items) == {}


def test_week_net_pessimistic_applies_factors():
    items = [
        _cf(week_t=1, direction="inflow", amount=Decimal("100"), certainty_layer="uncertain"),
        _cf(week_t=1, direction="outflow", amount=Decimal("50"), certainty_layer="uncertain"),
    ]
    wk = aggregate_layered(items)[1]
    neutral = week_net(wk, "neutral")
    pess = week_net(wk, "pessimistic")
    assert neutral == Decimal("50")
    # uncertain: inflow*0.7 - outflow*1.1 = 70 - 55 = 15
    assert pess == Decimal("15.0")


def test_week_band_only_for_uncertain():
    # 纯 deterministic 周不应有区间
    items_det = [_cf(week_t=1, amount=Decimal("100"), certainty_layer="deterministic")]
    wk_det = aggregate_layered(items_det)[1]
    assert week_band(wk_det, "neutral") == (None, None)

    items_u = [_cf(week_t=1, amount=Decimal("100"), certainty_layer="uncertain")]
    wk_u = aggregate_layered(items_u)[1]
    lower, upper = week_band(wk_u, "neutral")
    # uncertain inflow 100，区间宽 = 100 * 0.20 = 20，单边
    assert upper - lower == Decimal("40")


def test_compute_min_cash_fixed():
    rule = ReserveRule(entity_id="e", rule_type="fixed", fixed_value=Decimal("5000000"))
    mc = compute_min_cash([], rule, horizon=4)
    assert mc == [Decimal("5000000")] * 4


def test_compute_min_cash_rolling_coverage():
    rule = ReserveRule(entity_id="e", rule_type="rolling_coverage", rolling_weeks=2)
    items = [
        _cf(week_t=1, direction="outflow", category="payroll", amount=Decimal("10")),
        _cf(week_t=2, direction="outflow", category="tax", amount=Decimal("3")),
        _cf(week_t=3, direction="outflow", category="rent", amount=Decimal("2")),
        _cf(week_t=1, direction="outflow", category="purchase_payment", amount=Decimal("999")),  # 非刚性
    ]
    mc = compute_min_cash(items, rule, horizon=4)
    # MinCash[t] = rigid[t] + rigid[t+1]
    assert mc[0] == Decimal("13")  # 10 + 3
    assert mc[1] == Decimal("5")   # 3 + 2
    assert mc[2] == Decimal("2")   # 2 + 0
    assert mc[3] == Decimal("0")


def test_compute_min_cash_no_rule():
    assert compute_min_cash([], None, horizon=3) == [Decimal(0)] * 3


def test_serialize_layered_json_friendly():
    items = [_cf(week_t=1, amount=Decimal("10"), certainty_layer="uncertain")]
    by_week = aggregate_layered(items)
    dumped = serialize_layered(by_week)
    assert dumped[1]["uncertain"]["inflow"] == "10"
    # 序列化后金额是字符串（JSON 不丢精度）
    assert isinstance(dumped[1]["uncertain"]["inflow"], str)


def test_rigid_categories_known():
    # 防回归：刚性集合的稳定性
    assert RIGID_CATEGORIES == {"payroll", "tax", "interest", "principal_repay", "rent"}


def test_pessimistic_rules_defaults():
    # uncertain 层悲观因子最严：收 0.7 / 付 1.1
    assert DEFAULT_PESSIMISTIC.uncertain_inflow_factor == Decimal("0.70")
    assert DEFAULT_PESSIMISTIC.uncertain_outflow_factor == Decimal("1.10")
    # deterministic 层基本不动
    assert DEFAULT_PESSIMISTIC.deterministic_outflow_factor == Decimal("1.00")
