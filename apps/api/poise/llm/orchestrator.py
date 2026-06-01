"""对话编排：多轮 + tool dispatch + 历史持久化。

每轮逻辑：
1. 拉历史 + 新 user_message → 构造 messages 数组
2. 调 LLM（chat tier，with tools）
3. 若返回 tool_calls：逐个 dispatch，写 tool 消息，回到 2 继续
4. 否则返回 assistant 内容
最多迭代 N 次防止死循环（默认 5）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from poise.core.audit import record_event
from poise.core.rbac import CurrentUser
from poise.domain.models import Conversation, ConversationMessage
from poise.llm import client as llm_client
from poise.llm.prompts import render_system_prompt
from poise.llm.tools import TOOLS_SCHEMA, dispatch_tool

MAX_TOOL_ROUNDS = 8  # V4 thinking 模式可能多 tool 接力；留宽裕避免被截


@dataclass
class TurnResult:
    assistant_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_ms: int = 0
    model: str | None = None


def _build_message_history(db: Session, conversation: Conversation) -> list[dict[str, Any]]:
    """把 DB 中的历史消息转成 OpenAI Chat 协议格式。

    要点：DeepSeek V4 thinking 模式要求 assistant 消息把 reasoning_content
    原样回传，否则多轮会 400。
    """
    msgs: list[dict[str, Any]] = [{"role": "system", "content": render_system_prompt()}]
    for m in conversation.messages:
        if m.role == "user":
            msgs.append({"role": "user", "content": m.content or ""})
        elif m.role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
            if m.reasoning_content:
                entry["reasoning_content"] = m.reasoning_content
            if m.tool_args is not None and m.tool_call_id and m.tool_name:
                entry["tool_calls"] = [
                    {
                        "id": m.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": m.tool_name,
                            "arguments": json.dumps(m.tool_args, ensure_ascii=False),
                        },
                    }
                ]
            msgs.append(entry)
        elif m.role == "tool":
            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": m.tool_call_id or "",
                    "name": m.tool_name or "",
                    "content": json.dumps(m.tool_result or {}, ensure_ascii=False),
                }
            )
    return msgs


def run_turn(
    db: Session,
    user: CurrentUser,
    conversation: Conversation,
    user_message: str,
) -> TurnResult:
    """处理一轮对话（含可能的工具调用）。"""
    t0 = time.perf_counter()

    # 1. 写 user 消息
    db.add(
        ConversationMessage(
            conversation_id=conversation.id, role="user", content=user_message,
        )
    )
    db.flush()
    db.refresh(conversation)

    total_in, total_out = 0, 0
    last_model: str | None = None
    tool_calls_summary: list[dict[str, Any]] = []

    for _round in range(MAX_TOOL_ROUNDS):
        messages = _build_message_history(db, conversation)
        result = llm_client.chat(messages, tools=TOOLS_SCHEMA, tier="chat")
        total_in += result.tokens_in or 0
        total_out += result.tokens_out or 0
        last_model = result.model

        if not result.tool_calls:
            # LLM 给出最终回答
            db.add(
                ConversationMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=result.text or "",
                    reasoning_content=result.reasoning,
                    model=result.model,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                )
            )
            db.commit()
            db.refresh(conversation)
            elapsed = int((time.perf_counter() - t0) * 1000)
            record_event(
                db,
                actor_user_id=user.user_id,
                actor_role=user.role.value,
                event_type="llm.chat_turn",
                payload={
                    "conversation_id": conversation.id,
                    "model": result.model,
                    "tokens_in": total_in,
                    "tokens_out": total_out,
                    "tool_calls": [c["name"] for c in tool_calls_summary],
                    "elapsed_ms": elapsed,
                },
            )
            db.commit()
            return TurnResult(
                assistant_text=result.text or "",
                tool_calls=tool_calls_summary,
                tokens_in=total_in,
                tokens_out=total_out,
                elapsed_ms=elapsed,
                model=result.model,
            )

        # 2. 有 tool_calls：先持久化 assistant 的"调用意图"消息，再执行
        first_tc = result.tool_calls[0]  # MVP 假设一次只调一个；DeepSeek 通常如此
        try:
            args = json.loads(first_tc["arguments"]) if first_tc["arguments"] else {}
        except json.JSONDecodeError:
            args = {}
        db.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=result.text or "",
                reasoning_content=result.reasoning,
                tool_call_id=first_tc["id"],
                tool_name=first_tc["name"],
                tool_args=args,
                model=result.model,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
            )
        )
        db.flush()

        # 执行 tool
        tool_result = dispatch_tool(first_tc["name"], db, user, first_tc["arguments"] or "{}")

        db.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role="tool",
                tool_call_id=first_tc["id"],
                tool_name=first_tc["name"],
                tool_result=tool_result,
            )
        )
        db.flush()
        db.refresh(conversation)

        tool_calls_summary.append(
            {"name": first_tc["name"], "args": args, "result_keys": list(tool_result.keys())}
        )

    # 兜底：超出 MAX_TOOL_ROUNDS 仍未给出最终答复
    elapsed = int((time.perf_counter() - t0) * 1000)
    fallback = "（已尝试多轮调用工具但仍未得出最终结论。请追问以更明确的问题。）"
    db.add(
        ConversationMessage(
            conversation_id=conversation.id, role="assistant",
            content=fallback, model=last_model,
        )
    )
    db.commit()
    return TurnResult(
        assistant_text=fallback,
        tool_calls=tool_calls_summary,
        tokens_in=total_in,
        tokens_out=total_out,
        elapsed_ms=elapsed,
        model=last_model,
    )


def stream_turn(
    db: Session,
    user: CurrentUser,
    conversation: Conversation,
    user_message: str,
):
    """流式版本：逐 token yield 给前端。

    每个 yield 是一个 JSON-friendly dict，外层由 SSE endpoint 包装。
    """
    import time as _time
    t0 = _time.perf_counter()

    # 1. 写 user 消息
    db.add(ConversationMessage(conversation_id=conversation.id, role="user", content=user_message))
    db.flush()
    db.refresh(conversation)

    yield {"type": "begin", "conversation_id": conversation.id}

    total_in, total_out = 0, 0
    last_model: str | None = None

    for round_idx in range(MAX_TOOL_ROUNDS):
        messages = _build_message_history(db, conversation)
        yield {"type": "round", "round": round_idx + 1}

        text_buf: list[str] = []
        reasoning_buf: list[str] = []
        tool_calls_this_round: list[dict[str, Any]] = []
        finish_reason: str | None = None
        model = None
        ti, to = 0, 0

        for evt in llm_client.stream_chat(messages, tools=TOOLS_SCHEMA, tier="chat"):
            t = evt["type"]
            if t == "text":
                text_buf.append(evt["delta"])
                yield {"type": "text", "delta": evt["delta"]}
            elif t == "reasoning":
                reasoning_buf.append(evt["delta"])
                yield {"type": "reasoning", "delta": evt["delta"]}
            elif t == "tool_call":
                tool_calls_this_round.append(evt)
                yield {"type": "tool_call_request", "name": evt["name"], "id": evt["id"]}
            elif t == "done":
                finish_reason = evt.get("finish_reason")
                model = evt.get("model")
                ti = evt.get("tokens_in") or 0
                to = evt.get("tokens_out") or 0

        total_in += ti
        total_out += to
        last_model = model

        if not tool_calls_this_round:
            # 最终回答 —— 落库 + 完成
            db.add(
                ConversationMessage(
                    conversation_id=conversation.id, role="assistant",
                    content="".join(text_buf) or "",
                    reasoning_content="".join(reasoning_buf) or None,
                    model=model, tokens_in=ti, tokens_out=to,
                )
            )
            db.commit()
            elapsed = int((_time.perf_counter() - t0) * 1000)
            record_event(
                db, actor_user_id=user.user_id, actor_role=user.role.value,
                event_type="llm.chat_turn_stream",
                payload={
                    "conversation_id": conversation.id, "model": model,
                    "tokens_in": total_in, "tokens_out": total_out,
                    "elapsed_ms": elapsed,
                },
            )
            db.commit()
            yield {
                "type": "done",
                "tokens_in": total_in, "tokens_out": total_out,
                "elapsed_ms": elapsed, "model": model,
            }
            return

        # 有 tool_calls —— 持久化 assistant intent + 执行 + 持久化 tool 返回
        first_tc = tool_calls_this_round[0]
        try:
            args = json.loads(first_tc["arguments"]) if first_tc["arguments"] else {}
        except json.JSONDecodeError:
            args = {}
        db.add(
            ConversationMessage(
                conversation_id=conversation.id, role="assistant",
                content="".join(text_buf) or "",
                reasoning_content="".join(reasoning_buf) or None,
                tool_call_id=first_tc["id"], tool_name=first_tc["name"], tool_args=args,
                model=model, tokens_in=ti, tokens_out=to,
            )
        )
        db.flush()

        yield {"type": "tool_call_running", "name": first_tc["name"], "args": args}
        tool_result = dispatch_tool(first_tc["name"], db, user, first_tc["arguments"] or "{}")
        db.add(
            ConversationMessage(
                conversation_id=conversation.id, role="tool",
                tool_call_id=first_tc["id"], tool_name=first_tc["name"],
                tool_result=tool_result,
            )
        )
        db.flush()
        db.refresh(conversation)
        yield {"type": "tool_call_done", "name": first_tc["name"], "result_keys": list(tool_result.keys())}

    elapsed = int((_time.perf_counter() - t0) * 1000)
    yield {"type": "max_rounds", "elapsed_ms": elapsed, "tokens_in": total_in, "tokens_out": total_out}
