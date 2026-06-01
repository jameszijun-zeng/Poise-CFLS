"""CSV → 标准数据契约 → 落库。

接口：
    import_demo_company(db, seed_dir, anchor_date) -> ImportSummary
    import_csv_file(db, table_name, file_path, ...) -> ImportSummary

设计：
- 同一文件按 entity_code + 自然键（code / account_code+as_of_date 等）做 upsert
- 失败行（error）跳过；warning 行仍入库但记录
- 所有写入用 record_event() 落 AuditLog
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.audit import record_event
from poise.data_integration import quality_gate as qg
from poise.domain.models import (
    Account,
    BalanceSnapshot,
    CashFlowItem,
    CreditLine,
    Entity,
    Instrument,
    ReserveRule,
)
from poise.domain.schemas import ImportIssue, ImportSummary

DEFAULT_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seeds" / "demo_company"


# ----- 小工具 -----


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _get_entity_by_code(db: Session, code: str) -> Entity | None:
    return db.scalar(select(Entity).where(Entity.code == code))


def _get_account_by_code(db: Session, entity_id: str, code: str) -> Account | None:
    return db.scalar(
        select(Account).where(Account.entity_id == entity_id, Account.code == code)
    )


def _get_instrument_by_code(db: Session, entity_id: str, code: str) -> Instrument | None:
    return db.scalar(
        select(Instrument).where(Instrument.entity_id == entity_id, Instrument.code == code)
    )


# ----- 各表导入 -----


def _import_entities(db: Session, rows: list[dict[str, Any]], summary: ImportSummary) -> None:
    table = "entities"
    for idx, raw in enumerate(rows, start=2):
        code = (raw.get("code") or "").strip()
        name = (raw.get("name") or "").strip()
        if not code or not name:
            summary.issues.append(qg.issue(table, idx, "error", "code 或 name 缺失"))
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        existing = _get_entity_by_code(db, code)
        if existing:
            existing.name = name
            existing.base_currency = (raw.get("base_currency") or "CNY").strip()
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
        else:
            db.add(Entity(code=code, name=name, base_currency=(raw.get("base_currency") or "CNY").strip()))
            summary.imported[table] = summary.imported.get(table, 0) + 1
    db.flush()


def _import_accounts(db: Session, rows: list[dict[str, Any]], summary: ImportSummary) -> None:
    table = "accounts"
    for idx, raw in enumerate(rows, start=2):
        issues, norm = qg.validate_account_row(idx, raw)
        summary.issues.extend(issues)
        if norm is None:
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        entity = _get_entity_by_code(db, norm["entity_code"])
        if not entity:
            summary.issues.append(qg.issue(table, idx, "error", f"未知 entity_code={norm['entity_code']}"))
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        existing = _get_account_by_code(db, entity.id, norm["code"])
        if existing:
            for k in ("name", "bank_name", "account_number", "currency", "account_type"):
                setattr(existing, k, norm[k])
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
        else:
            db.add(
                Account(
                    entity_id=entity.id,
                    code=norm["code"],
                    name=norm["name"],
                    bank_name=norm["bank_name"],
                    account_number=norm["account_number"],
                    currency=norm["currency"],
                    account_type=norm["account_type"],
                )
            )
            summary.imported[table] = summary.imported.get(table, 0) + 1
    db.flush()


def _import_balances(db: Session, rows: list[dict[str, Any]], summary: ImportSummary) -> None:
    table = "balance_snapshots"
    for idx, raw in enumerate(rows, start=2):
        issues, norm = qg.validate_balance_row(idx, raw)
        summary.issues.extend(issues)
        if norm is None:
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        entity = _get_entity_by_code(db, norm["entity_code"])
        if not entity:
            summary.issues.append(qg.issue(table, idx, "error", f"未知 entity_code={norm['entity_code']}"))
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        account = _get_account_by_code(db, entity.id, norm["account_code"])
        if not account:
            summary.issues.append(qg.issue(table, idx, "error", f"未知 account_code={norm['account_code']}"))
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        # 同 (account, as_of_date) 视为 upsert
        existing = db.scalar(
            select(BalanceSnapshot).where(
                BalanceSnapshot.account_id == account.id,
                BalanceSnapshot.as_of_date == norm["as_of_date"],
            )
        )
        if existing:
            for k in ("balance", "available_balance", "restricted_balance", "currency", "source"):
                setattr(existing, k, norm[k])
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
        else:
            db.add(
                BalanceSnapshot(
                    entity_id=entity.id,
                    account_id=account.id,
                    as_of_date=norm["as_of_date"],
                    balance=norm["balance"],
                    available_balance=norm["available_balance"],
                    restricted_balance=norm["restricted_balance"],
                    currency=norm["currency"],
                    source=norm["source"],
                )
            )
            summary.imported[table] = summary.imported.get(table, 0) + 1
    db.flush()


def _import_cashflows(db: Session, rows: list[dict[str, Any]], anchor: date, summary: ImportSummary) -> None:
    table = "cash_flow_items"
    # 同一 entity 下，先清掉同 as_of (anchor) 之后未来 13 周内的现有项，避免重复
    by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    valid_rows: list[tuple[Entity, dict[str, Any]]] = []
    for idx, raw in enumerate(rows, start=2):
        issues, norm = qg.validate_cashflow_row(idx, raw, anchor)
        summary.issues.extend(issues)
        if norm is None:
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        entity = _get_entity_by_code(db, norm["entity_code"])
        if not entity:
            summary.issues.append(qg.issue(table, idx, "error", f"未知 entity_code={norm['entity_code']}"))
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        valid_rows.append((entity, norm))
        by_entity[entity.id].append(norm)

    # 清旧（按 entity 范围）
    for entity_id in by_entity:
        from sqlalchemy import delete  # local import to keep header clean

        db.execute(delete(CashFlowItem).where(CashFlowItem.entity_id == entity_id))
    db.flush()

    for entity, norm in valid_rows:
        account_id = None
        if norm.get("account_code"):
            acc = _get_account_by_code(db, entity.id, norm["account_code"])
            if acc:
                account_id = acc.id
        db.add(
            CashFlowItem(
                entity_id=entity.id,
                account_id=account_id,
                direction=norm["direction"],
                category=norm["category"],
                source_type=norm["source_type"],
                expected_date=norm["expected_date"],
                week_t=norm["week_t"],
                amount=norm["amount"],
                currency=norm["currency"],
                certainty_layer=norm["certainty_layer"],
                counterparty=norm["counterparty"],
                notes=norm["notes"],
            )
        )
        summary.imported[table] = summary.imported.get(table, 0) + 1
    db.flush()


def _import_instruments(db: Session, rows: list[dict[str, Any]], summary: ImportSummary) -> None:
    table = "instruments"
    for idx, raw in enumerate(rows, start=2):
        issues, norm = qg.validate_instrument_row(idx, raw)
        summary.issues.extend(issues)
        if norm is None:
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        entity = _get_entity_by_code(db, norm["entity_code"])
        if not entity:
            summary.issues.append(qg.issue(table, idx, "error", f"未知 entity_code={norm['entity_code']}"))
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        existing = _get_instrument_by_code(db, entity.id, norm["code"])
        if existing:
            for k in (
                "name",
                "kind",
                "liquidity_tier",
                "rate",
                "tenor_options",
                "min_amount",
                "max_amount",
                "redeemable",
                "redeem_cost",
                "counterparty",
                "whitelisted",
                "finance_priority",
                "currency",
                "notes",
            ):
                setattr(existing, k, norm[k])
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
        else:
            db.add(
                Instrument(
                    entity_id=entity.id,
                    code=norm["code"],
                    name=norm["name"],
                    kind=norm["kind"],
                    liquidity_tier=norm["liquidity_tier"],
                    rate=norm["rate"],
                    tenor_options=norm["tenor_options"],
                    min_amount=norm["min_amount"],
                    max_amount=norm["max_amount"],
                    redeemable=norm["redeemable"],
                    redeem_cost=norm["redeem_cost"],
                    counterparty=norm["counterparty"],
                    whitelisted=norm["whitelisted"],
                    finance_priority=norm["finance_priority"],
                    currency=norm["currency"],
                    notes=norm["notes"],
                )
            )
            summary.imported[table] = summary.imported.get(table, 0) + 1
    db.flush()


def _import_credit_lines(db: Session, rows: list[dict[str, Any]], summary: ImportSummary) -> None:
    table = "credit_lines"
    for idx, raw in enumerate(rows, start=2):
        issues, norm = qg.validate_credit_line_row(idx, raw)
        summary.issues.extend(issues)
        if norm is None:
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        entity = _get_entity_by_code(db, norm["entity_code"])
        if not entity:
            summary.issues.append(qg.issue(table, idx, "error", f"未知 entity_code={norm['entity_code']}"))
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        instrument_id = None
        if norm["instrument_code"]:
            inst = _get_instrument_by_code(db, entity.id, norm["instrument_code"])
            instrument_id = inst.id if inst else None
        existing = db.scalar(
            select(CreditLine).where(
                CreditLine.entity_id == entity.id, CreditLine.code == norm["code"]
            )
        )
        if existing:
            for k in ("bank_name", "limit_amount", "used_amount", "rate", "expires_at", "notes"):
                setattr(existing, k, norm[k])
            existing.instrument_id = instrument_id
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
        else:
            db.add(
                CreditLine(
                    entity_id=entity.id,
                    instrument_id=instrument_id,
                    bank_name=norm["bank_name"],
                    code=norm["code"],
                    limit_amount=norm["limit_amount"],
                    used_amount=norm["used_amount"],
                    rate=norm["rate"],
                    expires_at=norm["expires_at"],
                    notes=norm["notes"],
                )
            )
            summary.imported[table] = summary.imported.get(table, 0) + 1
    db.flush()


def _import_reserve_rules(db: Session, rows: list[dict[str, Any]], summary: ImportSummary) -> None:
    table = "reserve_rules"
    for idx, raw in enumerate(rows, start=2):
        issues, norm = qg.validate_reserve_rule_row(idx, raw)
        summary.issues.extend(issues)
        if norm is None:
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        entity = _get_entity_by_code(db, norm["entity_code"])
        if not entity:
            summary.issues.append(qg.issue(table, idx, "error", f"未知 entity_code={norm['entity_code']}"))
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
            continue
        # 一个 entity 一条规则；后导入覆盖前
        existing = db.scalar(select(ReserveRule).where(ReserveRule.entity_id == entity.id))
        if existing:
            for k in ("rule_type", "fixed_value", "rolling_weeks", "notes"):
                setattr(existing, k, norm[k])
            summary.skipped[table] = summary.skipped.get(table, 0) + 1
        else:
            db.add(
                ReserveRule(
                    entity_id=entity.id,
                    rule_type=norm["rule_type"],
                    fixed_value=norm["fixed_value"],
                    rolling_weeks=norm["rolling_weeks"],
                    notes=norm["notes"],
                )
            )
            summary.imported[table] = summary.imported.get(table, 0) + 1
    db.flush()


# ----- 顶层入口 -----


def import_demo_company(
    db: Session,
    seed_dir: Path | None = None,
    anchor_date: date | None = None,
    *,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> ImportSummary:
    """导入 demo_company 全量种子数据。顺序：entities → accounts → instruments →
    credit_lines → reserve_rules → balances → cashflows。"""

    seed_dir = seed_dir or DEFAULT_SEED_DIR
    if not seed_dir.exists():
        raise FileNotFoundError(f"seed dir not found: {seed_dir}")

    # 取 balances.csv 中最早 as_of_date 作为 anchor；否则用入参或当前日
    if anchor_date is None:
        try:
            bal_rows = _read_csv(seed_dir / "balances.csv")
            dates = [
                qg.parse_date(r["as_of_date"])
                for r in bal_rows
                if r.get("as_of_date")
            ]
            seed_d = min(d for d in dates if d is not None)
            anchor_date = qg.week_anchor_from_seed(seed_d)
        except Exception:
            from datetime import datetime
            anchor_date = qg.week_anchor_from_seed(datetime.now().date())

    summary = ImportSummary()

    _import_entities(db, _read_csv(seed_dir / "entities.csv"), summary)
    _import_accounts(db, _read_csv(seed_dir / "accounts.csv"), summary)
    _import_instruments(db, _read_csv(seed_dir / "instruments.csv"), summary)
    _import_credit_lines(db, _read_csv(seed_dir / "credit_lines.csv"), summary)
    _import_reserve_rules(db, _read_csv(seed_dir / "reserve_rules.csv"), summary)
    _import_balances(db, _read_csv(seed_dir / "balances.csv"), summary)
    _import_cashflows(db, _read_csv(seed_dir / "cashflows.csv"), anchor_date, summary)

    summary.ok = not any(i.severity == "error" for i in summary.issues)

    record_event(
        db,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        event_type="data.import_demo",
        payload={
            "seed_dir": str(seed_dir),
            "anchor": anchor_date.isoformat(),
            "imported": summary.imported,
            "skipped": summary.skipped,
            "error_count": sum(1 for i in summary.issues if i.severity == "error"),
        },
        notes="import_demo_company",
    )
    db.commit()
    return summary
