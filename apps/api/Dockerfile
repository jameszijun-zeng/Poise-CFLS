FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=600 \
    PIP_RETRIES=20

WORKDIR /app

# 项目依赖全部走 wheel，无需 build-essential。
# 国内 CDN 镜像在大型 arm64 wheel 上反复出现 SSL EOF / hash 不一致；
# 默认走 PyPI 官方源（最稳定），慢但确定能成功。
# 如确需国内加速，可在 docker compose 通过 build args 覆盖 PIP_INDEX_URL。

COPY pyproject.toml ./

# Layer 1：核心依赖（FastAPI + DB + Celery + LLM SDK + dev 工具）
RUN pip install -e ".[dev]"

# Layer 2：ML 栈（Phase 2/3 用；scipy 33MB / numpy 16MB / pandas 12MB）
# 大文件在受限网络下偶发 hash/EOF；失败不阻塞镜像，可后续 `make api-install-ml` 重试。
RUN pip install -e ".[ml]" || echo "WARN: ML layer install failed; re-run 'pip install -e \".[ml]\"' inside container before Phase 2/3."

COPY . .

EXPOSE 8000

CMD ["uvicorn", "poise.main:app", "--host", "0.0.0.0", "--port", "8000"]
