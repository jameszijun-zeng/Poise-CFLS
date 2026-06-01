"""FastAPI 应用入口。"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from poise import __version__
from poise.api.v1 import api_v1
from poise.core.audit import AuditLogMiddleware
from poise.core.config import get_settings

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

settings = get_settings()

app = FastAPI(
    title="稳盈 / Poise · CFLS API",
    description="资金预测与流动性管理策略智能体 · 后端 API",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditLogMiddleware)

app.include_router(api_v1)


@app.get("/healthz", tags=["health"], include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}
