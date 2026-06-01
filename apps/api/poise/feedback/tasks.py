"""Celery 任务（feedback 域）。

Celery Beat 每周一 06:00 触发 weekly_rolling_rerun；也可通过 API 手动触发。
任务发到 optimize 队列（重队列），避免阻塞默认队列。
"""

from __future__ import annotations

from poise.core.celery_app import celery_app
from poise.core.database import SessionLocal
from poise.feedback.rolling import run_rolling_cycle


@celery_app.task(name="poise.feedback.tasks.weekly_rolling_rerun")
def weekly_rolling_rerun(entity_id: str | None = None) -> dict:
    """周一 06:00 滚动重跑：锁定上周 → MAPE → EMA 偏差更新 → 新预测。"""
    with SessionLocal() as db:
        result = run_rolling_cycle(db, entity_id=entity_id, triggered_by="scheduler")
    return {
        "rolling_run_id": result.rolling_run_id,
        "new_forecast_id": result.new_forecast_id,
        "actual_rows": result.actual_rows,
        "bias_updates_count": result.bias_updates_count,
        "elapsed_ms": result.elapsed_ms,
    }
