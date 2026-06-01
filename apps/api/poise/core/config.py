from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://poise:poise_dev@postgres:5432/poise"
    )

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = (
        "db+postgresql+psycopg://poise:poise_dev@postgres:5432/poise"
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "change-me-in-prod"
    api_jwt_alg: str = "HS256"
    api_jwt_expire_minutes: int = 720
    api_cors_origins: str = "http://localhost:3000"

    # LLM
    llm_provider: Literal["deepseek", "openai"] = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model_chat: str = "deepseek-chat"
    deepseek_model_lite: str = "deepseek-chat"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_chat: str = "gpt-4o"
    openai_model_lite: str = "gpt-4o-mini"

    # Solver
    # 默认 CBC（pulp 内置，稳定）；HiGHS 性能更优但 pulp 3.3+highspy 1.14
    # 在 binary 决策模型上偶发 slack 解析 IndexError，故 MVP 默认 CBC，
    # 通过设置 SOLVER_BACKEND=highs 启用 HiGHS（pulp 修复后切换默认）。
    solver_backend: Literal["highs", "cbc"] = "cbc"
    # 单档求解时限：13 周 × 10 品种规模在收紧 big-M 后 CBC 通常 ≤ 5s；设 10s 留余地。
    solver_time_limit_sec: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
