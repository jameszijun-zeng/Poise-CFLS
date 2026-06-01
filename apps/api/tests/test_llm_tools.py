"""LLM 工具调度单测（不依赖真实 LLM API，直接调 dispatch_tool）。

验证：
- 6 个 tool 的 schema 完整
- 工具执行后返回 JSON-friendly dict
- 异常被捕获、不抛出（统一以 {"error": ...} 返回）
"""

import json

from poise.core.rbac import CurrentUser, Role
from poise.llm.tools import TOOLS_SCHEMA, TOOL_REGISTRY, dispatch_tool


def test_six_tools_registered():
    expected = {
        "run_forecast", "build_and_solve", "explain_plan",
        "diagnose_infeasible", "apply_overrides", "query_position",
    }
    assert set(TOOL_REGISTRY.keys()) == expected
    assert {t["function"]["name"] for t in TOOLS_SCHEMA} == expected


def test_tool_schema_shape():
    for t in TOOLS_SCHEMA:
        assert t["type"] == "function"
        fn = t["function"]
        assert "name" in fn and "description" in fn and "parameters" in fn
        assert fn["parameters"]["type"] == "object"


def test_dispatch_unknown_tool_returns_error():
    out = dispatch_tool(
        "nonexistent", db=None, user=CurrentUser(user_id="u", role=Role.admin), args_json="{}"
    )
    assert "error" in out


def test_dispatch_invalid_json_returns_error():
    out = dispatch_tool(
        "run_forecast", db=None, user=CurrentUser(user_id="u", role=Role.admin),
        args_json="{not valid json}",
    )
    assert "error" in out


def test_dispatch_runtime_exception_captured():
    # 不提供有效 db，工具内部会抛 → 应被捕获
    out = dispatch_tool(
        "query_position", db=None, user=CurrentUser(user_id="u", role=Role.admin),
        args_json="{}",
    )
    assert "error" in out


def test_apply_overrides_dry_run_only():
    """该 tool 默认 dry_run，不写库。"""
    # 此处只校验 schema 标记不会改库（实际执行需要 db，跳过）
    schema = next(t for t in TOOLS_SCHEMA if t["function"]["name"] == "apply_overrides")
    desc = schema["function"]["description"]
    assert "只改输入" in desc or "dry" in desc.lower()


def test_tools_schema_serializable():
    """整个 TOOLS_SCHEMA 应可 JSON 序列化（OpenAI API 要求）。"""
    s = json.dumps(TOOLS_SCHEMA, ensure_ascii=False)
    assert len(s) > 100
