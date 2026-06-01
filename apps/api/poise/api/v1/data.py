"""数据域只读 API + 触发 demo 导入。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.database import get_db
from poise.core.rbac import CurrentUser, get_current_user, require
from poise.data_integration.importers import import_demo_company
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
    BalanceSnapshotOut,
    CashFlowItemOut,
    CreditLineOut,
    EntityOut,
    ImportSummary,
    InstrumentOut,
    ReserveRuleOut,
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
