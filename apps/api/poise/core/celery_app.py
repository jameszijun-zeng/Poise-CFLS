from celery import Celery
from celery.schedules import crontab

from poise.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "poise",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=[
        "poise.feedback.tasks",
    ],
)

celery_app.conf.update(
    task_default_queue="default",
    task_routes={
        "poise.optimization.*": {"queue": "optimize"},
        "poise.feedback.*": {"queue": "optimize"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="Asia/Shanghai",
    enable_utc=False,
)

# Phase 6 反馈学习闭环：每周一 06:00 触发滚动重跑
celery_app.conf.beat_schedule = {
    "weekly-rolling-rerun": {
        "task": "poise.feedback.tasks.weekly_rolling_rerun",
        "schedule": crontab(minute=0, hour=6, day_of_week=1),
        "options": {"queue": "optimize"},
    },
}
