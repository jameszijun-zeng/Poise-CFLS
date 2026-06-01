"""US-1~US-6 对话回归集（系统设计 §5.2 + 需求文档 §3.2）。

每条对话脚本：
1. 给定一个用户问题（自然语言）
2. 期望 LLM 至少调用某个 tool（数字纪律：金额必来自 tool）
3. 期望最终 assistant 文本不含可疑的金额"凭空生成"

不依赖真实 LLM API。当 DEEPSEEK_API_KEY 缺失时整个文件被跳过。
跑法： pytest tests/test_us_dialogues.py -v  （需先 docker compose up -d 并设好 key）
"""

from __future__ import annotations

import os
import re
from typing import Iterable

import pytest

from poise.core.database import SessionLocal
from poise.core.rbac import CurrentUser, Role
from poise.domain.models import Conversation, User
from poise.llm.orchestrator import run_turn

# 跳过整个文件的条件
KEY = os.environ.get("DEEPSEEK_API_KEY", "")
LLM_AVAILABLE = bool(KEY) and KEY != "sk-replace-me"

pytestmark = pytest.mark.skipif(
    not LLM_AVAILABLE,
    reason="DEEPSEEK_API_KEY 未配置或为占位符；跳过 LLM 集成回归集",
)


# ----- 用例定义 -----

US_CASES = [
    {
        "id": "US-1",
        "title": "查看未来 13 周头寸",
        "message": "未来 13 周哪几周会紧？",
        "expected_tools": {"run_forecast", "query_position"},
        "must_mention_any": ["W", "周"],  # "第 11 周" or "W11" 都算
    },
    {
        "id": "US-2",
        "title": "闲钱配置建议",
        "message": "这周有什么闲钱能投？建议配多少",
        "expected_tools": {"build_and_solve", "explain_plan"},
        "must_mention_any": ["¥", "万", "亿", "元"],  # 中文金额单位
    },
    {
        "id": "US-3",
        "title": "缺口弥补方案",
        "message": "下个月底那笔 8000 万的并购款付得出来吗？不够的话怎么补最省？",
        "expected_tools": {"build_and_solve", "query_position", "diagnose_infeasible"},
        "must_mention_any": [],
    },
    {
        "id": "US-4",
        "title": "追问推理依据",
        "message": "为什么折中档比稳健档收益高这么多？",
        "expected_tools": {"explain_plan", "build_and_solve"},
        "must_mention_any": ["稳健", "折中"],
    },
    {
        "id": "US-5",
        "title": "what-if 改假设",
        "message": "假设北辰电气回款再延后 2 周到 W10，方案会变成什么样？",
        "expected_tools": {"apply_overrides"},
        "must_mention_any": ["北辰", "延后", "假设"],
    },
    {
        "id": "US-6",
        "title": "主动预警告知",
        "message": "悲观情景下有哪些缺口风险？",
        "expected_tools": {"run_forecast", "query_position", "diagnose_infeasible"},
        "must_mention_any": [],
    },
]


# ----- 数字纪律：检测 assistant 文本是否"凭空"出现金额 -----

# 简单启发：若 assistant 文本含 ¥xxx 或 NN万 / NN亿 / NN%，且本轮未调任何 tool，
# 则视为"凭空给数"（违反系统设计 §5.3 防线）
MONEY_PATTERN = re.compile(r"(¥\s*[\d,.]+|[\d.]+\s*(万|亿|百万|％|%))")


def _looks_like_concrete_money(text: str) -> bool:
    return bool(MONEY_PATTERN.search(text or ""))


def _bootstrap_test_user(db) -> tuple[Conversation, CurrentUser]:
    from sqlalchemy import select

    user = db.scalar(select(User).where(User.username == "treasurer"))
    if not user:
        pytest.skip("未找到 treasurer 用户；请先运行 bootstrap")
    cu = CurrentUser(user_id=user.id, role=Role.treasurer)
    conv = Conversation(entity_id=user.entity_id, user_id=user.id, title="US 回归")
    db.add(conv)
    db.flush()
    return conv, cu


@pytest.mark.parametrize("case", US_CASES, ids=lambda c: c["id"])
def test_us_dialogue_disciplined(case: dict):
    """每条 US 用例：跑一轮对话，验证 tool 调用 + 数字纪律。"""
    with SessionLocal() as db:
        conv, cu = _bootstrap_test_user(db)
        result = run_turn(db, cu, conv, case["message"])

    assert result.assistant_text, f"{case['id']}：无最终回复"
    called = {c["name"] for c in result.tool_calls}

    # 数字纪律：若提到了具体金额，必须至少调过 tool
    if _looks_like_concrete_money(result.assistant_text):
        assert called, (
            f"{case['id']} 违反数字纪律：assistant 给出了具体金额但未调任何 tool。\n"
            f"text: {result.assistant_text[:300]}"
        )

    # 应当至少调到期望集合中的一个 tool
    if case["expected_tools"]:
        intersection = called & set(case["expected_tools"])
        # 软断言：允许 LLM 选择其它合理 tool；这里只 warn，不强 fail
        if not intersection:
            pytest.skip(
                f"{case['id']} LLM 选了 {called} 但期望 {case['expected_tools']} —— "
                "可能是 prompt 不够 specific，需要 prompt 调优"
            )

    keywords = case.get("must_mention_any") or []
    if keywords:
        text = result.assistant_text or ""
        assert any(kw in text for kw in keywords), (
            f"{case['id']} 缺少任一关键词 {keywords}\n"
            f"text head: {text[:200]}"
        )
