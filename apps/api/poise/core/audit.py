"""AuditLog 中间件 + 通用事件记录器。

记录两类事件：
1. HTTP 写操作（POST/PUT/PATCH/DELETE）→ 中间件自动拦截
2. LLM 调用、方案采纳、参数覆盖等业务事件 → 业务代码显式调用 record_event()
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from poise.core.database import SessionLocal
from poise.domain.models import AuditLog

_logger = structlog.get_logger(__name__)

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_AUDIT_SKIP_PATHS = {"/api/v1/auth/login", "/healthz"}


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        if (
            request.method in _WRITE_METHODS
            and request.url.path not in _AUDIT_SKIP_PATHS
            and not request.url.path.startswith("/docs")
            and not request.url.path.startswith("/openapi")
        ):
            user = getattr(request.state, "current_user", None)
            try:
                with SessionLocal() as db:
                    db.add(
                        AuditLog(
                            actor_user_id=getattr(user, "user_id", None),
                            actor_role=getattr(user, "role", None).value
                            if user
                            else None,
                            event_type="http.request",
                            method=request.method,
                            path=request.url.path,
                            status_code=response.status_code,
                            duration_ms=duration_ms,
                            payload=None,
                        )
                    )
                    db.commit()
            except Exception as e:  # noqa: BLE001
                _logger.warning("audit_log_failed", error=str(e))

        return response


def record_event(
    db: Any,
    *,
    actor_user_id: str | None,
    actor_role: str | None,
    event_type: str,
    payload: dict | None = None,
    path: str | None = None,
    notes: str | None = None,
) -> None:
    """业务事件记录入口（LLM 调用、方案采纳、demo 导入等）。"""
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            event_type=event_type,
            path=path,
            payload=payload,
            notes=notes,
        )
    )
    db.flush()
