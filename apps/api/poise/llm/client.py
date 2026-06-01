"""LLM 客户端封装 —— DeepSeek 默认 / OpenAI 热备。

设计：
- 用 openai>=1.x SDK 统一访问；DeepSeek 兼容 OpenAI 协议，只需换 base_url + api_key
- 分层模型：deepseek-chat (V4) 跑解释/推理；deepseek-chat（同名）也兼任轻量路由
- prompt caching：DeepSeek 自动按前缀命中缓存（系统 prompt + 工具定义）
- 不在客户端层做对话状态管理；状态由 orchestrator 维护
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from poise.core.config import get_settings

Tier = Literal["chat", "lite"]


@dataclass
class CompletionResult:
    """同步调用结果（流式见 stream_chat）。"""

    text: str | None
    reasoning: str | None  # DeepSeek V4 thinking 模式产出
    tool_calls: list[dict[str, Any]]
    finish_reason: str | None
    model: str
    tokens_in: int | None
    tokens_out: int | None
    raw: ChatCompletion


def get_client() -> tuple[OpenAI, dict[Tier, str], str]:
    """返回 (client, {tier: model_name}, provider_label)。"""
    s = get_settings()
    if s.llm_provider == "deepseek":
        if not s.deepseek_api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY 未配置；请在 .env 中设置 DEEPSEEK_API_KEY="
                "<your key>，或将 LLM_PROVIDER 改为 openai。"
            )
        client = OpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_base_url)
        return (
            client,
            {"chat": s.deepseek_model_chat, "lite": s.deepseek_model_lite},
            "deepseek",
        )
    # openai 兜底
    if not s.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY 未配置；请在 .env 中设置 OPENAI_API_KEY 或切换 LLM_PROVIDER。"
        )
    client = OpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url)
    return client, {"chat": s.openai_model_chat, "lite": s.openai_model_lite}, "openai"


def chat(
    messages: list[ChatCompletionMessageParam],
    *,
    tools: list[dict[str, Any]] | None = None,
    tier: Tier = "chat",
    temperature: float = 0.2,
    max_tokens: int = 1500,
) -> CompletionResult:
    """单次调用（非流式）。"""
    client, model_map, _provider = get_client()
    model = model_map[tier]

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    msg = choice.message
    tool_calls_raw = msg.tool_calls or []
    tool_calls = [
        {
            "id": tc.id,
            "name": tc.function.name,
            "arguments": tc.function.arguments,  # raw JSON 字符串
        }
        for tc in tool_calls_raw
    ]
    # DeepSeek V4 / R1 等 thinking 模型把推理过程放在 reasoning_content；非标准字段
    reasoning = getattr(msg, "reasoning_content", None)
    usage = resp.usage
    return CompletionResult(
        text=msg.content,
        reasoning=reasoning,
        tool_calls=tool_calls,
        finish_reason=choice.finish_reason,
        model=model,
        tokens_in=usage.prompt_tokens if usage else None,
        tokens_out=usage.completion_tokens if usage else None,
        raw=resp,
    )


def stream_chat(
    messages: list[ChatCompletionMessageParam],
    *,
    tools: list[dict[str, Any]] | None = None,
    tier: Tier = "chat",
    temperature: float = 0.2,
    max_tokens: int = 1500,
):
    """流式调用 —— 增量产出文本/推理 token 与 tool_calls。

    yield 的字典格式：
      {"type": "text",      "delta": str}              文本增量
      {"type": "reasoning", "delta": str}              推理增量（V4 thinking）
      {"type": "tool_call", "id": str, "name": str, "args": str}  完整 tool call
      {"type": "done", "text": str, "reasoning": str, "tool_calls": list,
       "finish_reason": str, "model": str, "tokens_in": int, "tokens_out": int}
    """
    client, model_map, _provider = get_client()
    model = model_map[tier]

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    text_buf: list[str] = []
    reasoning_buf: list[str] = []
    # tool_calls 流式：openai 协议会把 tool_call 按 index 分片传
    tool_acc: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None
    usage_tokens_in: int | None = None
    usage_tokens_out: int | None = None

    stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        if chunk.usage:
            usage_tokens_in = chunk.usage.prompt_tokens
            usage_tokens_out = chunk.usage.completion_tokens
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta
        if choice.finish_reason:
            finish_reason = choice.finish_reason

        if delta.content:
            text_buf.append(delta.content)
            yield {"type": "text", "delta": delta.content}
        # DeepSeek V4 thinking 的推理流
        r = getattr(delta, "reasoning_content", None)
        if r:
            reasoning_buf.append(r)
            yield {"type": "reasoning", "delta": r}
        # tool_calls 流式拼接
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index if tc.index is not None else 0
                slot = tool_acc.setdefault(idx, {"id": "", "name": "", "args": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function.arguments:
                        slot["args"] += tc.function.arguments

    # 把拼好的 tool calls 一次性 yield 出来
    final_tool_calls: list[dict[str, Any]] = []
    for idx in sorted(tool_acc.keys()):
        slot = tool_acc[idx]
        if slot["name"]:
            final_tool_calls.append({"id": slot["id"], "name": slot["name"], "arguments": slot["args"]})
            yield {
                "type": "tool_call",
                "id": slot["id"], "name": slot["name"], "arguments": slot["args"],
            }

    yield {
        "type": "done",
        "text": "".join(text_buf),
        "reasoning": "".join(reasoning_buf) or None,
        "tool_calls": final_tool_calls,
        "finish_reason": finish_reason,
        "model": model,
        "tokens_in": usage_tokens_in,
        "tokens_out": usage_tokens_out,
    }
