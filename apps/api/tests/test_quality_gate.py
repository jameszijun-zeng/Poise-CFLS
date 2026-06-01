from datetime import date

from poise.data_integration import quality_gate as qg


ANCHOR = date(2026, 5, 25)  # Monday W0


def _good_cashflow_row():
    return {
        "entity_code": "DEMO",
        "account_code": "ACC-BASIC",
        "direction": "inflow",
        "category": "sales_collection",
        "source_type": "ar",
        "expected_date": "2026-06-01",
        "amount": "1000000.00",
        "currency": "CNY",
        "certainty_layer": "deterministic",
        "counterparty": "客户A",
        "notes": "",
    }


def test_valid_cashflow_passes():
    issues, norm = qg.validate_cashflow_row(2, _good_cashflow_row(), ANCHOR)
    assert norm is not None
    assert not any(i.severity == "error" for i in issues)
    assert norm["week_t"] == 2  # 2026-06-01 is week 2 (W0 anchor 5-25)


def test_bad_direction_rejected():
    row = _good_cashflow_row()
    row["direction"] = "sideways"
    issues, norm = qg.validate_cashflow_row(2, row, ANCHOR)
    assert norm is None
    assert any(i.field == "direction" and i.severity == "error" for i in issues)


def test_negative_amount_rejected():
    row = _good_cashflow_row()
    row["amount"] = "-100"
    issues, norm = qg.validate_cashflow_row(2, row, ANCHOR)
    assert norm is None


def test_huge_amount_warns():
    row = _good_cashflow_row()
    row["amount"] = "2000000000"  # 20亿
    issues, norm = qg.validate_cashflow_row(2, row, ANCHOR)
    assert norm is not None  # warning only, still passes
    assert any(i.severity == "warning" and "异常" in i.message for i in issues)


def test_invest_requires_liquidity_tier():
    row = {
        "entity_code": "DEMO",
        "code": "MMF-X",
        "name": "测试货基",
        "kind": "invest",
        "liquidity_tier": "",
        "rate_annual_pct": "2.30",
        "tenor_options_weeks": "0",
        "min_amount": "1000000",
        "max_amount": "",
        "redeemable": "True",
        "redeem_cost_pct": "0",
        "counterparty": "X",
        "whitelisted": "True",
        "finance_priority": "",
        "currency": "CNY",
        "notes": "",
    }
    issues, norm = qg.validate_instrument_row(2, row)
    assert norm is None
    assert any(i.field == "liquidity_tier" for i in issues)


def test_credit_used_gt_limit_rejected():
    row = {
        "entity_code": "DEMO",
        "instrument_code": "LOAN-WC",
        "bank_name": "X",
        "code": "WC-001",
        "limit_amount": "1000",
        "used_amount": "2000",
        "rate_annual_pct": "4.35",
        "expires_at": "",
        "notes": "",
    }
    issues, norm = qg.validate_credit_line_row(2, row)
    assert norm is None
    assert any("used_amount > limit_amount" in i.message for i in issues)


def test_reserve_rolling_requires_weeks():
    row = {
        "entity_code": "DEMO",
        "rule_type": "rolling_coverage",
        "fixed_value": "",
        "rolling_weeks": "",
        "notes": "",
    }
    issues, norm = qg.validate_reserve_rule_row(2, row)
    assert norm is None
    assert any(i.field == "rolling_weeks" for i in issues)


def test_week_from_date_in_range():
    # ANCHOR=2026-05-25 (Mon)，2026-06-15 (Mon W4)
    assert qg.week_from_date(date(2026, 6, 15), ANCHOR) == 4
    assert qg.week_from_date(date(2026, 5, 25), ANCHOR) == 1
    assert qg.week_from_date(date(2026, 8, 17), ANCHOR) == 13
    assert qg.week_from_date(date(2026, 8, 24), ANCHOR) is None  # over horizon
