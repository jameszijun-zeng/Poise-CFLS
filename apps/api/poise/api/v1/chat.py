"""对话 REST API。"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.database import get_db
from poise.core.rbac import CurrentUser, require
from poise.domain.models import Conversation, ConversationMessage, User
from poise.domain.schemas import (
    ChatTurnRequest,
    ChatTurnResponse,
    ConversationFullOut,
    ConversationMessageOut,
    ConversationOut,
)
from poise.llm.orchestrator import run_turn, stream_turn
from poise.core.database import SessionLocal

try:
    from openai import APIError as _LLMAPIError
    from openai import AuthenticationError as _LLMAuthError
except ImportError:  # pragma: no cover
    _LLMAuthError = _LLMAPIError = Exception  # type: ignore

router = APIRouter(prefix="/chat", tags=["chat"])
DbDep = Annotated[Session, Depends(get_db)]


def _get_or_create_conversation(
    db: Session, user: CurrentUser, conv_id: str | None, title_hint: str | None
) -> Conversation:
    if conv_id:
        conv = db.get(Conversation, conv_id)
        if not conv:
            raise HTTPException(404, "conversation not found")
        if conv.user_id != user.user_id:
            raise HTTPException(403, "无权访问他人的会话")
        return conv
    db_user = db.get(User, user.user_id)
    if not db_user:
        raise HTTPException(403, "用户记录缺失")
    conv = Conversation(
        entity_id=db_user.entity_id,
        user_id=user.user_id,
        title=(title_hint or "新对话")[:80],
    )
    db.add(conv)
    db.flush()
    return conv


@router.post("/turn", response_model=ChatTurnResponse)
def chat_turn(
    body: ChatTurnRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("chat.use"))],
) -> ChatTurnResponse:
    conv = _get_or_create_conversation(
        db, user, body.conversation_id, body.title_hint or body.message[:40]
    )
    try:
        result = run_turn(db, user, conv, body.message)
    except RuntimeError as e:
        # 配置缺失（DEEPSEEK_API_KEY 未设等）
        raise HTTPException(status_code=503, detail=f"LLM 未配置: {e}") from e
    except _LLMAuthError as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM 鉴权失败：请在 .env 中提供有效的 DEEPSEEK_API_KEY 后重启 api 容器。原始错误: {e}",
        ) from e
    except _LLMAPIError as e:
        raise HTTPException(status_code=502, detail=f"LLM 服务异常: {e}") from e

    return ChatTurnResponse(
        conversation_id=conv.id,
        assistant_text=result.assistant_text,
        tool_calls=result.tool_calls,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        elapsed_ms=result.elapsed_ms,
        model=result.model,
    )


@router.post("/turn-stream")
def chat_turn_stream(
    body: ChatTurnRequest,
    user: Annotated[CurrentUser, Depends(require("chat.use"))],
) -> StreamingResponse:
    """流式版本：返回 SSE（Server-Sent Events），每行一个 JSON 事件。

    事件类型：begin / round / text / reasoning / tool_call_request /
              tool_call_running / tool_call_done / done / error
    """
    def gen():
        # 每个请求独立 session，避免 generator 跨 request 复用导致 detached
        with SessionLocal() as db:
            try:
                conv = _get_or_create_conversation(
                    db, user, body.conversation_id, body.title_hint or body.message[:40]
                )
                for evt in stream_turn(db, user, conv, body.message):
                    yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
            except _LLMAuthError as e:
                yield f"data: {json.dumps({'type':'error','code':'auth','message':str(e)}, ensure_ascii=False)}\n\n"
            except _LLMAPIError as e:
                yield f"data: {json.dumps({'type':'error','code':'api','message':str(e)}, ensure_ascii=False)}\n\n"
            except Exception as e:  # noqa: BLE001
                yield f"data: {json.dumps({'type':'error','code':'internal','message':str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("chat.use"))],
    limit: int = Query(20, ge=1, le=100),
) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user.user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
    )


@router.get("/conversations/{conv_id}", response_model=ConversationFullOut)
def get_conversation(
    conv_id: str,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require("chat.use"))],
) -> ConversationFullOut:
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "conversation not found")
    if conv.user_id != user.user_id:
        raise HTTPException(403, "无权访问")
    msgs = list(
        db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conv_id)
            .order_by(ConversationMessage.id)
        )
    )
    return ConversationFullOut(
        id=conv.id, entity_id=conv.entity_id, user_id=conv.user_id,
        title=conv.title, created_at=conv.created_at, updated_at=conv.updated_at,
        messages=[ConversationMessageOut.model_validate(m) for m in msgs],
    )
