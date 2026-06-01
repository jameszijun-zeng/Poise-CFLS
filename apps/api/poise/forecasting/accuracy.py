"""MAPE 看板 —— Phase 2 出骨架，Phase 6 反馈学习闭环填充。

MVP 提供：
- 按 (week_t, layer, direction, category) 计算 MAPE，要求有 "actual" 列入对照
- 此处仅返回结构占位，等 Phase 6 引入 ActualCashFlow 表后接通
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class MapeBucket:
    layer: str
    category: str | None
    direction: str | None
    sample_count: int
    mape: Decimal | None  # 无样本则 None


def empty_accuracy_payload() -> dict:
    """Phase 6 接通前的空看板结构。"""
    return {
        "by_layer": [
            {"layer": "deterministic", "sample_count": 0, "mape": None},
            {"layer": "pattern", "sample_count": 0, "mape": None},
            {"layer": "uncertain", "sample_count": 0, "mape": None},
        ],
        "by_category": [],
        "note": "MAPE 在 Phase 6 反馈学习闭环上线后开始累计。",
    }
