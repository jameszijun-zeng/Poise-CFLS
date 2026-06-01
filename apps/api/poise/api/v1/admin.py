"""管理后台 API —— 用户管理 + 审计日志检索。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from poise.core.audit import record_event
from poise.core.database import get_db
from poise.core.rbac import CurrentUser, Role, require
from poise.core.security import hash_password
from poise.domain.models import AuditLog, User
from poise.domain.schemas import AuditLogOut, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])
DbDep = Annotated[Session, Depends(get_db)]


# ----- Schemas -----


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=6, max_length=72)
    role: Role


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=72)


class AuditLogPage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    total: int
    items: list[AuditLogOut]


# ----- 用户管理 -----


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("user.manage"))],
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at)))


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreateRequest,
    db: DbDep,
    actor: Annotated[CurrentUser, Depends(require("user.manage"))],
) -> User:
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, f"username 已存在：{body.username}")
    actor_user = db.get(User, actor.user_id)
    if not actor_user:
        raise HTTPException(500, "actor user 缺失")
    u = User(
        entity_id=actor_user.entity_id,
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role.value,
        is_active=True,
    )
    db.add(u)
    db.flush()
    record_event(
        db,
        actor_user_id=actor.user_id, actor_role=actor.role.value,
        event_type="admin.user_create",
        payload={"target_user_id": u.id, "target_role": u.role, "target_username": u.username},
    )
    db.commit()
    db.refresh(u)
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdateRequest,
    db: DbDep,
    actor: Annotated[CurrentUser, Depends(require("user.manage"))],
) -> User:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "user not found")
    diff: dict = {}
    if body.display_name is not None and body.display_name != u.display_name:
        diff["display_name"] = (u.display_name, body.display_name)
        u.display_name = body.display_name
    if body.role is not None and body.role.value != u.role:
        diff["role"] = (u.role, body.role.value)
        u.role = body.role.value
    if body.is_active is not None and body.is_active != u.is_active:
        diff["is_active"] = (u.is_active, body.is_active)
        u.is_active = body.is_active
    if body.password:
        u.password_hash = hash_password(body.password)
        diff["password"] = ("***", "***")
    record_event(
        db,
        actor_user_id=actor.user_id, actor_role=actor.role.value,
        event_type="admin.user_update",
        payload={"target_user_id": u.id, "diff": diff},
    )
    db.commit()
    db.refresh(u)
    return u


# ----- 审计日志检索 -----


@router.get("/audit-logs", response_model=AuditLogPage)
def list_audit_logs(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("audit.read"))],
    event_type: str | None = Query(None, description="模糊匹配"),
    actor_user_id: str | None = Query(None),
    actor_role: str | None = Query(None),
    hours: int | None = Query(None, ge=1, le=24 * 30, description="最近 N 小时"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AuditLogPage:
    conds = []
    if event_type:
        conds.append(AuditLog.event_type.like(f"%{event_type}%"))
    if actor_user_id:
        conds.append(AuditLog.actor_user_id == actor_user_id)
    if actor_role:
        conds.append(AuditLog.actor_role == actor_role)
    if hours:
        since = datetime.utcnow() - timedelta(hours=hours)
        conds.append(AuditLog.occurred_at >= since)

    base = select(AuditLog).where(and_(*conds)) if conds else select(AuditLog)
    # count
    from sqlalchemy import func as sa_func

    total_stmt = (
        select(sa_func.count()).select_from(AuditLog).where(and_(*conds))
        if conds else select(sa_func.count()).select_from(AuditLog)
    )
    total = int(db.scalar(total_stmt) or 0)
    items = list(
        db.scalars(base.order_by(AuditLog.id.desc()).limit(limit).offset(offset))
    )
    return AuditLogPage(
        total=total,
        items=[AuditLogOut.model_validate(i) for i in items],
    )


@router.get("/audit-logs/event-types", response_model=list[str])
def list_event_types(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require("audit.read"))],
) -> list[str]:
    """所有出现过的 event_type，便于前端做下拉过滤。"""
    from sqlalchemy import distinct as sa_distinct
    rows = db.scalars(
        select(sa_distinct(AuditLog.event_type)).order_by(AuditLog.event_type)
    )
    return list(rows)
