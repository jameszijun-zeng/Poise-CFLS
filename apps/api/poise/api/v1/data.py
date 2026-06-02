"""数据域 API ：只读列表 + 手工 CRUD + CSV 导入（demo / 上传两种）。"""

from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.audit import record_event
from poise.core.database import get_db
from poise.core.rbac import CurrentUser, require
from poise.data_integration.adapters import ADAPTER_REGISTRY
from poise.data_integration.importers import (
    DEFAULT_SEED_DIR,
    import_demo_company,
    import_from_adapter,
)
from poise.data_integration.quality_gate import week_anchor_from_seed
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
from poise.domain.schemas import (
    AccountOut,
    AccountUpsert,
    BalanceSnapshotOut,
    BalanceSnapshotUpsert,
    CashFlowItemOut,
    CashFlowItemUpsert,
    CreditLineOut,
    CreditLineUpsert,
    CsvUploadPreview,
    EntityOut,
    ImportIssue,
    ImportSummary,
    InstrumentOut,
    InstrumentUpsert,
    ReserveRuleOut,
    ReserveRuleUpsert,
)

router = APIRouter(prefix="/data", tags=["data"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/entities", response_model=list[EntityOut])
def list_entities(db: DbDep, _: Annotated[CurrentUser, Depends(require("data.read"))]) -> list[Entity]:
    return list(db.scalars(select(Entity).order_by(Entity.created_at)))


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
) -> list[Account]:
    stmt = select(Account)
    if entity_id:
        stmt = stmt.where(Account.entity_id == entity_id)
    return list(db.scalars(stmt.order_by(Account.code)))


@router.get("/balances", response_model=list[BalanceSnapshotOut])
def list_balances(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
) -> list[BalanceSnapshot]:
    stmt = select(BalanceSnapshot)
    if entity_id:
        stmt = stmt.where(BalanceSnapshot.entity_id == entity_id)
    return list(db.scalars(stmt.order_by(BalanceSnapshot.as_of_date.desc())))


@router.get("/cashflows", response_model=list[CashFlowItemOut])
def list_cashflows(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
    direction: str | None = Query(None, pattern="^(inflow|outflow)$"),
    category: str | None = Query(None),
    week_t: int | None = Query(None, ge=1, le=13),
    limit: int = Query(500, ge=1, le=2000),
) -> list[CashFlowItem]:
    stmt = select(CashFlowItem)
    if entity_id:
        stmt = stmt.where(CashFlowItem.entity_id == entity_id)
    if direction:
        stmt = stmt.where(CashFlowItem.direction == direction)
    if category:
        stmt = stmt.where(CashFlowItem.category == category)
    if week_t is not None:
        stmt = stmt.where(CashFlowItem.week_t == week_t)
    stmt = stmt.order_by(CashFlowItem.expected_date).limit(limit)
    return list(db.scalars(stmt))


@router.get("/instruments", response_model=list[InstrumentOut])
def list_instruments(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
    kind: str | None = Query(None, pattern="^(invest|finance)$"),
) -> list[Instrument]:
    stmt = select(Instrument)
    if entity_id:
        stmt = stmt.where(Instrument.entity_id == entity_id)
    if kind:
        stmt = stmt.where(Instrument.kind == kind)
    return list(db.scalars(stmt.order_by(Instrument.kind, Instrument.finance_priority, Instrument.code)))


@router.get("/credit-lines", response_model=list[CreditLineOut])
def list_credit_lines(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
) -> list[CreditLine]:
    stmt = select(CreditLine)
    if entity_id:
        stmt = stmt.where(CreditLine.entity_id == entity_id)
    return list(db.scalars(stmt.order_by(CreditLine.bank_name)))


@router.get("/reserve-rules", response_model=list[ReserveRuleOut])
def list_reserve_rules(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("data.read"))],
    entity_id: str | None = Query(None),
) -> list[ReserveRule]:
    stmt = select(ReserveRule)
    if entity_id:
        stmt = stmt.where(ReserveRule.entity_id == entity_id)
    return list(db.scalars(stmt))


@router.post("/import-demo", response_model=ImportSummary)
def trigger_import_demo(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> ImportSummary:
    """触发 demo_company 全量种子数据导入（幂等）。"""
    return import_demo_company(
        db,
        actor_user_id=user.user_id,
        actor_role=user.role.value,
    )


# =====================================================================
# 手工 CRUD —— 6 张表（accounts / balances / cashflows / instruments /
# credit-lines / reserve-rules）。POST 创建，PATCH 部分字段更新，DELETE 删除。
#
# 设计：
# - 所有写入都走 record_event() 落 AuditLog，含 diff
# - PATCH 只更新非 None 字段
# - 新建时必填字段由 schema layer 校验缺失，service layer 校验业务合法性
# =====================================================================


def _entity_id(db: Session) -> str:
    """单体 MVP：自动取唯一 entity。"""
    ents = list(db.scalars(select(Entity)))
    if len(ents) != 1:
        raise HTTPException(400, "未找到唯一 entity；多主体场景请显式传入")
    return ents[0].id


def _apply_patch(obj, patch_dict: dict, allowed: set[str]) -> dict:
    """把 patch_dict（非 None 项）写入 obj，返回 diff。"""
    diff = {}
    for k, v in patch_dict.items():
        if v is None or k not in allowed:
            continue
        old = getattr(obj, k, None)
        if old != v:
            diff[k] = {"old": _jsonable(old), "new": _jsonable(v)}
            setattr(obj, k, v)
    return diff


def _jsonable(v):
    from datetime import date as _d, datetime as _dt
    from decimal import Decimal as _D

    if isinstance(v, (_d, _dt)):
        return v.isoformat()
    if isinstance(v, _D):
        return str(v)
    return v


# ----- Account -----


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(
    body: AccountUpsert,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> Account:
    if not body.code or not body.name:
        raise HTTPException(400, "code 和 name 为必填")
    eid = _entity_id(db)
    if db.scalar(select(Account).where(Account.entity_id == eid, Account.code == body.code)):
        raise HTTPException(409, f"账户编码已存在：{body.code}")
    a = Account(
        entity_id=eid,
        code=body.code, name=body.name,
        bank_name=body.bank_name, account_number=body.account_number,
        currency=body.currency or "CNY", account_type=body.account_type or "basic",
        is_active=body.is_active if body.is_active is not None else True,
        notes=body.notes,
    )
    db.add(a)
    db.flush()
    record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                 event_type="data.account_create",
                 payload={"id": a.id, "code": a.code, "name": a.name})
    db.commit()
    db.refresh(a)
    return a


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_account(
    account_id: str, body: AccountUpsert, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> Account:
    a = db.get(Account, account_id)
    if not a:
        raise HTTPException(404, "account not found")
    diff = _apply_patch(a, body.model_dump(), {
        "code", "name", "bank_name", "account_number",
        "currency", "account_type", "is_active", "notes",
    })
    if diff:
        record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                     event_type="data.account_update",
                     payload={"id": a.id, "diff": diff})
    db.commit()
    db.refresh(a)
    return a


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(
    account_id: str, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
):
    a = db.get(Account, account_id)
    if not a:
        raise HTTPException(404, "account not found")
    # 软删除：is_active=False 而非 DELETE，避免外键引用断裂
    a.is_active = False
    record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                 event_type="data.account_deactivate",
                 payload={"id": a.id, "code": a.code})
    db.commit()
    return None


# ----- BalanceSnapshot -----


@router.post("/balances", response_model=BalanceSnapshotOut, status_code=201)
def create_balance(
    body: BalanceSnapshotUpsert, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> BalanceSnapshot:
    if not body.account_id or body.as_of_date is None or body.balance is None:
        raise HTTPException(400, "account_id / as_of_date / balance 为必填")
    acct = db.get(Account, body.account_id)
    if not acct:
        raise HTTPException(400, "account_id 不存在")
    b = BalanceSnapshot(
        entity_id=acct.entity_id, account_id=body.account_id, as_of_date=body.as_of_date,
        balance=body.balance,
        available_balance=body.available_balance if body.available_balance is not None else body.balance,
        restricted_balance=body.restricted_balance or 0,
        currency=body.currency or acct.currency,
        source=body.source or "manual",
    )
    db.add(b)
    db.flush()
    record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                 event_type="data.balance_create",
                 payload={"id": b.id, "account_id": b.account_id, "as_of": b.as_of_date.isoformat()})
    db.commit()
    db.refresh(b)
    return b


# ----- CashFlowItem -----


@router.post("/cashflows", response_model=CashFlowItemOut, status_code=201)
def create_cashflow(
    body: CashFlowItemUpsert, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> CashFlowItem:
    missing = [k for k in ("direction", "category", "source_type", "expected_date",
                           "amount", "certainty_layer") if getattr(body, k) is None]
    if missing:
        raise HTTPException(400, f"必填字段缺失：{missing}")
    if body.direction not in qg.DIRECTIONS:
        raise HTTPException(400, f"direction 非法：{body.direction}")
    if body.category not in qg.CATEGORIES:
        raise HTTPException(400, f"category 非法：{body.category}")
    if body.source_type not in qg.SOURCE_TYPES:
        raise HTTPException(400, f"source_type 非法：{body.source_type}")
    if body.certainty_layer not in qg.CERTAINTY_LAYERS:
        raise HTTPException(400, f"certainty_layer 非法：{body.certainty_layer}")
    if body.amount is None or body.amount <= 0:
        raise HTTPException(400, "amount 必须 > 0")

    eid = _entity_id(db)
    cf = CashFlowItem(
        entity_id=eid, account_id=body.account_id,
        direction=body.direction, category=body.category, source_type=body.source_type,
        expected_date=body.expected_date, week_t=body.week_t,
        amount=body.amount, currency=body.currency or "CNY",
        certainty_layer=body.certainty_layer,
        counterparty=body.counterparty, notes=body.notes,
    )
    db.add(cf)
    db.flush()
    record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                 event_type="data.cashflow_create",
                 payload={"id": cf.id, "amount": str(cf.amount), "week_t": cf.week_t})
    db.commit()
    db.refresh(cf)
    return cf


@router.patch("/cashflows/{item_id}", response_model=CashFlowItemOut)
def update_cashflow(
    item_id: str, body: CashFlowItemUpsert, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> CashFlowItem:
    cf = db.get(CashFlowItem, item_id)
    if not cf:
        raise HTTPException(404, "cashflow not found")
    diff = _apply_patch(cf, body.model_dump(), {
        "account_id", "direction", "category", "source_type",
        "expected_date", "week_t", "amount", "currency",
        "certainty_layer", "counterparty", "notes",
    })
    if diff:
        record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                     event_type="data.cashflow_update",
                     payload={"id": cf.id, "diff": diff})
    db.commit()
    db.refresh(cf)
    return cf


@router.delete("/cashflows/{item_id}", status_code=204)
def delete_cashflow(
    item_id: str, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
):
    cf = db.get(CashFlowItem, item_id)
    if not cf:
        raise HTTPException(404, "cashflow not found")
    record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                 event_type="data.cashflow_delete",
                 payload={"id": cf.id, "amount": str(cf.amount), "week_t": cf.week_t})
    db.delete(cf)
    db.commit()
    return None


# ----- Instrument -----


@router.post("/instruments", response_model=InstrumentOut, status_code=201)
def create_instrument(
    body: InstrumentUpsert, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> Instrument:
    missing = [k for k in ("code", "name", "kind", "rate", "tenor_options") if getattr(body, k) is None]
    if missing:
        raise HTTPException(400, f"必填字段缺失：{missing}")
    if body.kind not in qg.INSTRUMENT_KINDS:
        raise HTTPException(400, f"kind 非法：{body.kind}")
    if body.kind == "invest" and body.liquidity_tier not in qg.LIQUIDITY_TIERS:
        raise HTTPException(400, "invest 品种必须指定 liquidity_tier (cash/stable/yield)")
    eid = _entity_id(db)
    if db.scalar(select(Instrument).where(Instrument.entity_id == eid, Instrument.code == body.code)):
        raise HTTPException(409, f"品种编码已存在：{body.code}")
    inst = Instrument(
        entity_id=eid, code=body.code, name=body.name, kind=body.kind,
        liquidity_tier=body.liquidity_tier, rate=body.rate,
        tenor_options=body.tenor_options, min_amount=body.min_amount or 0,
        max_amount=body.max_amount,
        redeemable=body.redeemable if body.redeemable is not None else True,
        redeem_cost=body.redeem_cost or 0, counterparty=body.counterparty,
        whitelisted=body.whitelisted if body.whitelisted is not None else True,
        finance_priority=body.finance_priority, currency=body.currency or "CNY",
        notes=body.notes,
    )
    db.add(inst)
    db.flush()
    record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                 event_type="data.instrument_create",
                 payload={"id": inst.id, "code": inst.code, "kind": inst.kind})
    db.commit()
    db.refresh(inst)
    return inst


@router.patch("/instruments/{instrument_id}", response_model=InstrumentOut)
def update_instrument(
    instrument_id: str, body: InstrumentUpsert, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> Instrument:
    inst = db.get(Instrument, instrument_id)
    if not inst:
        raise HTTPException(404, "instrument not found")
    diff = _apply_patch(inst, body.model_dump(), {
        "code", "name", "kind", "liquidity_tier", "rate", "tenor_options",
        "min_amount", "max_amount", "redeemable", "redeem_cost",
        "counterparty", "whitelisted", "finance_priority", "currency", "notes",
    })
    if diff:
        record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                     event_type="data.instrument_update",
                     payload={"id": inst.id, "diff": diff})
    db.commit()
    db.refresh(inst)
    return inst


@router.delete("/instruments/{instrument_id}", status_code=204)
def delete_instrument(
    instrument_id: str, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
):
    inst = db.get(Instrument, instrument_id)
    if not inst:
        raise HTTPException(404, "instrument not found")
    # 软删除：whitelisted=False（保留历史记录用于已采纳方案审计）
    inst.whitelisted = False
    record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                 event_type="data.instrument_unwhitelist",
                 payload={"id": inst.id, "code": inst.code})
    db.commit()
    return None


# ----- CreditLine -----


@router.post("/credit-lines", response_model=CreditLineOut, status_code=201)
def create_credit_line(
    body: CreditLineUpsert, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> CreditLine:
    missing = [k for k in ("bank_name", "code", "limit_amount", "rate") if getattr(body, k) is None]
    if missing:
        raise HTTPException(400, f"必填字段缺失：{missing}")
    if body.used_amount and body.limit_amount and body.used_amount > body.limit_amount:
        raise HTTPException(400, "used_amount 不能超过 limit_amount")
    eid = _entity_id(db)
    cl = CreditLine(
        entity_id=eid, instrument_id=body.instrument_id,
        bank_name=body.bank_name, code=body.code,
        limit_amount=body.limit_amount, used_amount=body.used_amount or 0,
        rate=body.rate, expires_at=body.expires_at, notes=body.notes,
    )
    db.add(cl)
    db.flush()
    record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                 event_type="data.credit_line_create",
                 payload={"id": cl.id, "bank": cl.bank_name, "limit": str(cl.limit_amount)})
    db.commit()
    db.refresh(cl)
    return cl


@router.patch("/credit-lines/{cl_id}", response_model=CreditLineOut)
def update_credit_line(
    cl_id: str, body: CreditLineUpsert, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> CreditLine:
    cl = db.get(CreditLine, cl_id)
    if not cl:
        raise HTTPException(404, "credit line not found")
    new_limit = body.limit_amount if body.limit_amount is not None else cl.limit_amount
    new_used = body.used_amount if body.used_amount is not None else cl.used_amount
    if new_used > new_limit:
        raise HTTPException(400, "used_amount 不能超过 limit_amount")
    diff = _apply_patch(cl, body.model_dump(), {
        "instrument_id", "bank_name", "code", "limit_amount",
        "used_amount", "rate", "expires_at", "notes",
    })
    if diff:
        record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                     event_type="data.credit_line_update",
                     payload={"id": cl.id, "diff": diff})
    db.commit()
    db.refresh(cl)
    return cl


@router.delete("/credit-lines/{cl_id}", status_code=204)
def delete_credit_line(
    cl_id: str, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
):
    cl = db.get(CreditLine, cl_id)
    if not cl:
        raise HTTPException(404, "credit line not found")
    record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                 event_type="data.credit_line_delete",
                 payload={"id": cl.id, "code": cl.code, "bank": cl.bank_name})
    db.delete(cl)
    db.commit()
    return None


# ----- ReserveRule -----（一个 entity 通常一条；POST/PATCH 都行）


@router.put("/reserve-rules", response_model=ReserveRuleOut)
def upsert_reserve_rule(
    body: ReserveRuleUpsert, db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> ReserveRule:
    if body.rule_type not in qg.RESERVE_RULE_TYPES:
        raise HTTPException(400, f"rule_type 非法：{body.rule_type}")
    if body.rule_type == "fixed" and body.fixed_value is None:
        raise HTTPException(400, "fixed 规则必须指定 fixed_value")
    if body.rule_type == "rolling_coverage" and not body.rolling_weeks:
        raise HTTPException(400, "rolling_coverage 规则必须指定 rolling_weeks ≥ 1")
    eid = _entity_id(db)
    rule = db.scalar(select(ReserveRule).where(ReserveRule.entity_id == eid))
    if rule:
        diff = _apply_patch(rule, body.model_dump(),
                            {"rule_type", "fixed_value", "rolling_weeks", "notes"})
        record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                     event_type="data.reserve_rule_update",
                     payload={"id": rule.id, "diff": diff})
    else:
        rule = ReserveRule(entity_id=eid, rule_type=body.rule_type,
                           fixed_value=body.fixed_value, rolling_weeks=body.rolling_weeks,
                           notes=body.notes)
        db.add(rule)
        db.flush()
        record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                     event_type="data.reserve_rule_create",
                     payload={"id": rule.id, "type": rule.rule_type})
    db.commit()
    db.refresh(rule)
    return rule


# =====================================================================
# CSV 上传 —— 两步流程：
#   1) POST /data/upload-csv?table=cashflows&commit=false  →  预览 + 校验
#   2) POST /data/upload-csv?table=cashflows&commit=true   →  落库
# =====================================================================


_CSV_HANDLERS = {
    "accounts":     {"validator": qg.validate_account_row,    "skip_header_idx": 2},
    "balances":     {"validator": qg.validate_balance_row,    "skip_header_idx": 2},
    "cashflows":    {"validator": "_cf",                       "skip_header_idx": 2},
    "instruments":  {"validator": qg.validate_instrument_row, "skip_header_idx": 2},
    "credit_lines": {"validator": qg.validate_credit_line_row, "skip_header_idx": 2},
    "reserve_rules":{"validator": qg.validate_reserve_rule_row, "skip_header_idx": 2},
}


# =====================================================================
# Adapter 接入：通用入口，支持 csv_directory / excel_workbook / 自定义 ERP
# =====================================================================


from pydantic import BaseModel


class AdapterImportRequest(BaseModel):
    adapter: str
    kwargs: dict = {}


@router.get("/adapters", response_model=list[str])
def list_adapters(
    _: Annotated[CurrentUser, Depends(require("data.read"))],
) -> list[str]:
    """列出已注册的 SourceAdapter，便于前端 / CLI 按名调度。"""
    return list(ADAPTER_REGISTRY.keys())


@router.post("/import-from-adapter", response_model=ImportSummary)
def trigger_import_from_adapter(
    body: AdapterImportRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
) -> ImportSummary:
    """通用 adapter 入口。

    示例：
      {"adapter": "csv_directory", "kwargs": {"path": "/app/seeds/demo_company"}}
      {"adapter": "excel_workbook", "kwargs": {"path": "/tmp/client_data.xlsx"}}
      {"adapter": "erp_sap", "kwargs": {"company_code": "CN01", "from_date": "2026-06-01"}}

    自定义 ERP/银行 adapter 由 IT 在 poise.data_integration.adapters 中实现并
    register() 即可立刻通过本端点使用。
    """
    if body.adapter not in ADAPTER_REGISTRY:
        raise HTTPException(400, f"未知 adapter：{body.adapter}；已注册：{list(ADAPTER_REGISTRY)}")
    try:
        return import_from_adapter(
            db, body.adapter, body.kwargs,
            actor_user_id=user.user_id, actor_role=user.role.value,
        )
    except FileNotFoundError as e:
        raise HTTPException(400, str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"adapter 执行失败：{e}") from e


@router.post("/upload-excel", response_model=ImportSummary)
def upload_excel(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
    file: UploadFile = File(...),
) -> ImportSummary:
    """便捷端点：直接上传 Excel 工作簿（7 sheet 一一对应 7 张表）。"""
    import tempfile, os

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "仅支持 .xlsx / .xlsm 格式")
    fd, tmp = tempfile.mkstemp(suffix=".xlsx")
    try:
        os.write(fd, file.file.read())
        os.close(fd)
        return import_from_adapter(
            db, "excel_workbook", {"path": tmp},
            actor_user_id=user.user_id, actor_role=user.role.value,
        )
    except RuntimeError as e:  # openpyxl 缺失
        raise HTTPException(501, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Excel 导入失败：{e}") from e
    finally:
        try:
            os.unlink(tmp)
        except Exception:  # noqa: BLE001
            pass


@router.post("/upload-csv", response_model=CsvUploadPreview)
def upload_csv(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("data.write"))],
    table: str = Query(..., description="表名：accounts / balances / cashflows / instruments / credit_lines / reserve_rules"),
    commit: bool = Query(False, description="false=仅校验+预览；true=校验通过后写库"),
    file: UploadFile = File(...),
) -> CsvUploadPreview:
    if table not in _CSV_HANDLERS:
        raise HTTPException(400, f"不支持的表：{table}")
    raw = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw))
    rows = list(reader)

    issues: list[ImportIssue] = []
    sample = rows[:5]
    valid = 0

    # cashflows 校验需要 anchor 日期；取最早 expected_date
    anchor = None
    if table == "cashflows":
        from datetime import date as _d

        ds = []
        for r in rows:
            try:
                d = qg.parse_date(r.get("expected_date"))
                if d:
                    ds.append(d)
            except ValueError:
                pass
        anchor = week_anchor_from_seed(min(ds)) if ds else week_anchor_from_seed(_d.today())

    for idx, row in enumerate(rows, start=2):
        if table == "cashflows":
            iss, norm = qg.validate_cashflow_row(idx, row, anchor)
        else:
            iss, norm = _CSV_HANDLERS[table]["validator"](idx, row)
        issues.extend(iss)
        if norm is not None:
            valid += 1

    preview = CsvUploadPreview(
        table=table, total_rows=len(rows), valid_rows=valid,
        sample=sample, issues=issues[:30],   # 只回前 30 条 issue，避免 payload 过大
    )

    if commit:
        # 通过 importers 复用现有写入逻辑
        from poise.data_integration.importers import (
            _import_accounts, _import_balances, _import_cashflows,
            _import_credit_lines, _import_instruments, _import_reserve_rules,
        )
        summary = ImportSummary()
        try:
            if table == "accounts":
                _import_accounts(db, rows, summary)
            elif table == "balances":
                _import_balances(db, rows, summary)
            elif table == "cashflows":
                _import_cashflows(db, rows, anchor, summary)
            elif table == "instruments":
                _import_instruments(db, rows, summary)
            elif table == "credit_lines":
                _import_credit_lines(db, rows, summary)
            elif table == "reserve_rules":
                _import_reserve_rules(db, rows, summary)
            record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                         event_type="data.csv_upload",
                         payload={"table": table, "imported": summary.imported,
                                  "skipped": summary.skipped, "filename": file.filename},
                         notes=f"committed: {valid}/{len(rows)} valid")
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            raise HTTPException(500, f"写库失败：{e}") from e
    else:
        record_event(db, actor_user_id=user.user_id, actor_role=user.role.value,
                     event_type="data.csv_preview",
                     payload={"table": table, "valid_rows": valid,
                              "total": len(rows), "filename": file.filename})
        db.commit()

    return preview
