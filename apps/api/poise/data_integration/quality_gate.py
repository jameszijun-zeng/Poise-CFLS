"""数据质量门 —— 入模前拦截脏数据。

设计原则：宁可拒绝入库，不让脏数据污染下游引擎。
质量门返回 ImportIssue 列表，严重级 error 阻止入库，warning 仅提示。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from poise.domain.schemas import ImportIssue

# 业务字典
DIRECTIONS = {"inflow", "outflow"}
CATEGORIES = {
    "sales_collection",
    "purchase_payment",
    "payroll",
    "tax",
    "interest",
    "principal_repay",
    "rent",
    "other",
}
SOURCE_TYPES = {"contract", "ar", "ap", "order", "schedule", "statistical"}
CERTAINTY_LAYERS = {"deterministic", "pattern", "uncertain"}
INSTRUMENT_KINDS = {"invest", "finance"}
LIQUIDITY_TIERS = {"cash", "stable", "yield"}
ACCOUNT_TYPES = {"basic", "general", "special"}
RESERVE_RULE_TYPES = {"fixed", "rolling_coverage"}
SUPPORTED_CURRENCIES = {"CNY"}  # MVP 本币为主


def parse_amount(raw: str | float | int | Decimal | None, *, allow_empty: bool = False) -> Decimal | None:
    if raw is None or raw == "":
        return None if allow_empty else Decimal(0)
    if isinstance(raw, Decimal):
        return raw
    try:
        return Decimal(str(raw))
    except InvalidOperation as e:
        raise ValueError(f"金额格式无效：{raw}") from e


def parse_date(raw: str | date | None) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date):
        return raw
    return datetime.strptime(str(raw), "%Y-%m-%d").date()


def parse_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None or raw == "":
        return False
    s = str(raw).strip().lower()
    return s in {"1", "true", "yes", "y", "t"}


def week_from_date(d: date, anchor: date) -> int | None:
    """anchor=W0 起始周一。返回 1-based 周次，超界返回 None。"""
    delta = (d - anchor).days
    if delta < 0:
        return None
    week = delta // 7 + 1
    return week if 1 <= week <= 13 else None


def issue(table: str, row: int | None, severity: str, message: str, field: str | None = None) -> ImportIssue:
    return ImportIssue(table=table, row=row, severity=severity, message=message, field=field)


# ----- 各表逐行校验 -----


def validate_cashflow_row(idx: int, raw: dict[str, Any], anchor: date) -> tuple[list[ImportIssue], dict[str, Any] | None]:
    """返回 (issues, normalized) ；normalized 为 None 表示该行被拒。"""
    issues: list[ImportIssue] = []
    out: dict[str, Any] = {}

    direction = (raw.get("direction") or "").strip()
    if direction not in DIRECTIONS:
        issues.append(issue("cash_flow_items", idx, "error", f"direction 必须为 {DIRECTIONS}，当前 {direction!r}", "direction"))
    out["direction"] = direction

    category = (raw.get("category") or "").strip()
    if category not in CATEGORIES:
        issues.append(issue("cash_flow_items", idx, "error", f"category 不在受支持集合：{category!r}", "category"))
    out["category"] = category

    source_type = (raw.get("source_type") or "").strip()
    if source_type not in SOURCE_TYPES:
        issues.append(issue("cash_flow_items", idx, "error", f"source_type 无效：{source_type!r}", "source_type"))
    out["source_type"] = source_type

    cert = (raw.get("certainty_layer") or "").strip()
    if cert not in CERTAINTY_LAYERS:
        issues.append(issue("cash_flow_items", idx, "error", f"certainty_layer 无效：{cert!r}", "certainty_layer"))
    out["certainty_layer"] = cert

    try:
        d = parse_date(raw.get("expected_date"))
        if d is None:
            issues.append(issue("cash_flow_items", idx, "error", "expected_date 缺失", "expected_date"))
        else:
            out["expected_date"] = d
    except ValueError as e:
        issues.append(issue("cash_flow_items", idx, "error", str(e), "expected_date"))
        d = None

    # week_t：CSV 显式提供则校验；缺失则从日期推导
    w_raw = raw.get("week_t")
    if w_raw not in (None, ""):
        try:
            w = int(w_raw)
        except (TypeError, ValueError):
            w = -1
        if not 1 <= w <= 13:
            issues.append(issue("cash_flow_items", idx, "warning", f"week_t={w} 超出 1-13，将以日期重算", "week_t"))
            w = week_from_date(d, anchor) if d else None
        out["week_t"] = w
    elif d:
        out["week_t"] = week_from_date(d, anchor)
    else:
        out["week_t"] = None

    try:
        amt = parse_amount(raw.get("amount"))
        if amt is None or amt <= 0:
            issues.append(issue("cash_flow_items", idx, "error", "amount 必须为正数", "amount"))
        else:
            # 异常值检测：单笔超 10 亿（量级离群）
            if amt > Decimal("1_000_000_000"):
                issues.append(issue("cash_flow_items", idx, "warning", f"金额异常大：¥{amt}", "amount"))
            out["amount"] = amt
    except ValueError as e:
        issues.append(issue("cash_flow_items", idx, "error", str(e), "amount"))

    currency = (raw.get("currency") or "CNY").strip()
    if currency not in SUPPORTED_CURRENCIES:
        issues.append(issue("cash_flow_items", idx, "error", f"币种暂仅支持 {SUPPORTED_CURRENCIES}", "currency"))
    out["currency"] = currency

    out["counterparty"] = raw.get("counterparty") or None
    out["notes"] = raw.get("notes") or None
    out["entity_code"] = raw.get("entity_code")
    out["account_code"] = raw.get("account_code") or None

    has_error = any(i.severity == "error" for i in issues)
    return issues, None if has_error else out


def validate_account_row(idx: int, raw: dict[str, Any]) -> tuple[list[ImportIssue], dict[str, Any] | None]:
    issues: list[ImportIssue] = []
    out: dict[str, Any] = {
        "entity_code": raw.get("entity_code"),
        "code": (raw.get("code") or "").strip(),
        "name": (raw.get("name") or "").strip(),
        "bank_name": raw.get("bank_name") or None,
        "account_number": raw.get("account_number") or None,
        "currency": (raw.get("currency") or "CNY").strip(),
        "account_type": (raw.get("account_type") or "basic").strip(),
    }
    if not out["code"]:
        issues.append(issue("accounts", idx, "error", "code 缺失", "code"))
    if not out["name"]:
        issues.append(issue("accounts", idx, "error", "name 缺失", "name"))
    if out["account_type"] not in ACCOUNT_TYPES:
        issues.append(issue("accounts", idx, "error", f"account_type 无效：{out['account_type']!r}", "account_type"))
    if out["currency"] not in SUPPORTED_CURRENCIES:
        issues.append(issue("accounts", idx, "error", f"币种暂仅支持 {SUPPORTED_CURRENCIES}", "currency"))
    return issues, None if any(i.severity == "error" for i in issues) else out


def validate_instrument_row(idx: int, raw: dict[str, Any]) -> tuple[list[ImportIssue], dict[str, Any] | None]:
    issues: list[ImportIssue] = []
    kind = (raw.get("kind") or "").strip()
    tier = (raw.get("liquidity_tier") or None) or None
    if kind not in INSTRUMENT_KINDS:
        issues.append(issue("instruments", idx, "error", f"kind 无效：{kind!r}", "kind"))
    if kind == "invest":
        if tier not in LIQUIDITY_TIERS:
            issues.append(issue("instruments", idx, "error", f"投资品种必须指定 liquidity_tier，当前 {tier!r}", "liquidity_tier"))
    elif kind == "finance" and tier:
        issues.append(issue("instruments", idx, "warning", "融资品种不应设置 liquidity_tier，将忽略", "liquidity_tier"))
        tier = None

    try:
        rate_pct = parse_amount(raw.get("rate_annual_pct"))
    except ValueError as e:
        issues.append(issue("instruments", idx, "error", str(e), "rate_annual_pct"))
        rate_pct = Decimal(0)
    rate = (rate_pct or Decimal(0)) / Decimal(100)  # 转小数

    tenor_raw = (raw.get("tenor_options_weeks") or "").strip()
    try:
        tenor_options = [int(x) for x in tenor_raw.split("|")] if tenor_raw else [0]
    except ValueError:
        issues.append(issue("instruments", idx, "error", f"tenor_options_weeks 应为 | 分隔的整数：{tenor_raw!r}", "tenor_options_weeks"))
        tenor_options = []

    try:
        redeem_cost_pct = parse_amount(raw.get("redeem_cost_pct"), allow_empty=True) or Decimal(0)
    except ValueError as e:
        issues.append(issue("instruments", idx, "error", str(e), "redeem_cost_pct"))
        redeem_cost_pct = Decimal(0)
    redeem_cost = redeem_cost_pct / Decimal(100)

    try:
        min_amt = parse_amount(raw.get("min_amount"), allow_empty=True) or Decimal(0)
    except ValueError as e:
        issues.append(issue("instruments", idx, "error", str(e), "min_amount"))
        min_amt = Decimal(0)
    try:
        max_amt = parse_amount(raw.get("max_amount"), allow_empty=True)
    except ValueError as e:
        issues.append(issue("instruments", idx, "error", str(e), "max_amount"))
        max_amt = None

    fp_raw = raw.get("finance_priority")
    finance_priority = int(fp_raw) if fp_raw not in (None, "") else None

    out = {
        "entity_code": raw.get("entity_code"),
        "code": (raw.get("code") or "").strip(),
        "name": (raw.get("name") or "").strip(),
        "kind": kind,
        "liquidity_tier": tier,
        "rate": rate,
        "tenor_options": tenor_options,
        "min_amount": min_amt,
        "max_amount": max_amt,
        "redeemable": parse_bool(raw.get("redeemable")),
        "redeem_cost": redeem_cost,
        "counterparty": raw.get("counterparty") or None,
        "whitelisted": parse_bool(raw.get("whitelisted")),
        "finance_priority": finance_priority,
        "currency": (raw.get("currency") or "CNY").strip(),
        "notes": raw.get("notes") or None,
    }
    return issues, None if any(i.severity == "error" for i in issues) else out


def validate_credit_line_row(idx: int, raw: dict[str, Any]) -> tuple[list[ImportIssue], dict[str, Any] | None]:
    issues: list[ImportIssue] = []
    try:
        rate_pct = parse_amount(raw.get("rate_annual_pct"))
    except ValueError as e:
        issues.append(issue("credit_lines", idx, "error", str(e), "rate_annual_pct"))
        rate_pct = Decimal(0)
    try:
        limit = parse_amount(raw.get("limit_amount"))
        used = parse_amount(raw.get("used_amount"), allow_empty=True) or Decimal(0)
    except ValueError as e:
        issues.append(issue("credit_lines", idx, "error", str(e), "limit_amount/used_amount"))
        limit = used = Decimal(0)
    if limit is not None and used > limit:
        issues.append(issue("credit_lines", idx, "error", "used_amount > limit_amount", "used_amount"))
    try:
        expires_at = parse_date(raw.get("expires_at"))
    except ValueError as e:
        issues.append(issue("credit_lines", idx, "error", str(e), "expires_at"))
        expires_at = None

    out = {
        "entity_code": raw.get("entity_code"),
        "instrument_code": raw.get("instrument_code") or None,
        "bank_name": raw.get("bank_name"),
        "code": raw.get("code"),
        "limit_amount": limit,
        "used_amount": used,
        "rate": (rate_pct or Decimal(0)) / Decimal(100),
        "expires_at": expires_at,
        "notes": raw.get("notes") or None,
    }
    return issues, None if any(i.severity == "error" for i in issues) else out


def validate_reserve_rule_row(idx: int, raw: dict[str, Any]) -> tuple[list[ImportIssue], dict[str, Any] | None]:
    issues: list[ImportIssue] = []
    rt = (raw.get("rule_type") or "").strip()
    if rt not in RESERVE_RULE_TYPES:
        issues.append(issue("reserve_rules", idx, "error", f"rule_type 无效：{rt!r}", "rule_type"))
    fixed_value = None
    rolling_weeks = None
    if rt == "fixed":
        try:
            fixed_value = parse_amount(raw.get("fixed_value"))
        except ValueError as e:
            issues.append(issue("reserve_rules", idx, "error", str(e), "fixed_value"))
    elif rt == "rolling_coverage":
        rw_raw = raw.get("rolling_weeks")
        try:
            rolling_weeks = int(rw_raw) if rw_raw not in (None, "") else None
        except ValueError:
            issues.append(issue("reserve_rules", idx, "error", f"rolling_weeks 应为整数：{rw_raw!r}", "rolling_weeks"))
        if not rolling_weeks or rolling_weeks < 1:
            issues.append(issue("reserve_rules", idx, "error", "rolling_weeks 必须 ≥ 1", "rolling_weeks"))

    out = {
        "entity_code": raw.get("entity_code"),
        "rule_type": rt,
        "fixed_value": fixed_value,
        "rolling_weeks": rolling_weeks,
        "notes": raw.get("notes") or None,
    }
    return issues, None if any(i.severity == "error" for i in issues) else out


def validate_balance_row(idx: int, raw: dict[str, Any]) -> tuple[list[ImportIssue], dict[str, Any] | None]:
    issues: list[ImportIssue] = []
    try:
        bal = parse_amount(raw.get("balance"))
        avail = parse_amount(raw.get("available_balance"))
        restricted = parse_amount(raw.get("restricted_balance"), allow_empty=True) or Decimal(0)
        d = parse_date(raw.get("as_of_date"))
    except ValueError as e:
        issues.append(issue("balance_snapshots", idx, "error", str(e), "amount"))
        bal = avail = restricted = Decimal(0)
        d = None
    if d is None:
        issues.append(issue("balance_snapshots", idx, "error", "as_of_date 缺失", "as_of_date"))

    out = {
        "entity_code": raw.get("entity_code"),
        "account_code": raw.get("account_code"),
        "as_of_date": d,
        "balance": bal,
        "available_balance": avail,
        "restricted_balance": restricted,
        "currency": (raw.get("currency") or "CNY").strip(),
        "source": (raw.get("source") or "eod").strip(),
    }
    return issues, None if any(i.severity == "error" for i in issues) else out


def week_anchor_from_seed(seed_date: date) -> date:
    """从 anchor 日期取当周的周一作为 W0 起点。
    便于 expected_date → week_t 的归集。
    """
    return seed_date - timedelta(days=seed_date.weekday())
