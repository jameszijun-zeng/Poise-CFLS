from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from poise.core.security import decode_access_token


class Role(StrEnum):
    """RBAC 角色（10–20 人试点）。

    - admin     : 用户/权限/数据管理，全量
    - treasurer : 资金主管，可采纳方案、改假设、查看全部
    - analyst   : 出纳分析师，可问可调可建模，但不可采纳方案
    - viewer    : 只读（含上级查看）
    """

    admin = "admin"
    treasurer = "treasurer"
    analyst = "analyst"
    viewer = "viewer"


# 权限矩阵：哪些角色能执行某个操作
PERMISSIONS: dict[str, set[Role]] = {
    "user.manage": {Role.admin},
    "data.write": {Role.admin, Role.treasurer, Role.analyst},
    "data.read": {Role.admin, Role.treasurer, Role.analyst, Role.viewer},
    "forecast.run": {Role.admin, Role.treasurer, Role.analyst},
    "plan.solve": {Role.admin, Role.treasurer, Role.analyst},
    "plan.adopt": {Role.admin, Role.treasurer},
    "audit.read": {Role.admin, Role.treasurer},
    "chat.use": {Role.admin, Role.treasurer, Role.analyst},
}


class CurrentUser(BaseModel):
    user_id: str
    role: Role


_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(_oauth2_scheme)] = None,
) -> CurrentUser:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    user_id = payload.get("sub")
    role_raw = payload.get("role")
    if not user_id or not role_raw:
        raise HTTPException(status_code=401, detail="malformed token payload")
    try:
        role = Role(role_raw)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"unknown role: {role_raw}") from e

    user = CurrentUser(user_id=str(user_id), role=role)
    # 暴露给 AuditLog 中间件
    request.state.current_user = user
    return user


def require(*permissions: str) -> Callable[[CurrentUser], CurrentUser]:
    """权限装饰器工厂。

    用法：
        @router.post("/plans/{plan_id}/adopt")
        def adopt(user: CurrentUser = Depends(require("plan.adopt"))): ...
    """

    def _checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        for perm in permissions:
            allowed = PERMISSIONS.get(perm)
            if allowed is None:
                raise HTTPException(status_code=500, detail=f"unknown permission: {perm}")
            if user.role not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"role '{user.role}' lacks permission '{perm}'",
                )
        return user

    return _checker
