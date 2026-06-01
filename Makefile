.PHONY: help up down logs api-shell api-test api-fmt api-lint web-dev migrate revision seed api-install-ml demo demo-play demo-dry smoke

help:
	@echo "Poise / 稳盈 · 常用命令"
	@echo "  make up           # docker compose 启动全栈"
	@echo "  make down         # 停止"
	@echo "  make logs         # 查看 api 日志"
	@echo "  make migrate      # 应用 Alembic 迁移"
	@echo "  make revision m='msg'  # 生成新迁移"
	@echo "  make api-test     # 跑后端测试"
	@echo "  make api-lint     # ruff + mypy（host 上）"
	@echo "  make api-fmt      # ruff format"
	@echo "  make web-dev      # 仅启前端"
	@echo "  make seed         # 导入 demo_company 种子数据"
	@echo "  make smoke        # 端到端冒烟（10 步，< 2s）"
	@echo "  make demo         # 录制 demo 视频（含数据重置）"
	@echo "  make demo-play    # 仅自动演示，不重置"
	@echo "  make demo-dry     # 仅打印演示步骤"

smoke:
	bash scripts/smoke.sh

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

api-shell:
	docker compose exec api bash

api-test:
	docker compose exec api pytest -q

# 静态分析在 host 上跑（容器内不装 ruff/mypy，避免国内 CDN 不稳）
# 首次：cd apps/api && pip install -e ".[lint]"
api-lint:
	cd apps/api && ruff check . && mypy poise

api-fmt:
	cd apps/api && ruff format .

migrate:
	docker compose exec api alembic upgrade head

revision:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

web-dev:
	pnpm --filter @poise/web dev

seed:
	docker compose exec api python -m poise.data_integration.cli import-demo

# 若 Docker build 阶段 ML 层失败（受限网络下 scipy/numpy/pandas 大文件偶发），
# 用此命令在运行容器内重装；可重复执行直到成功。
api-install-ml:
	docker compose exec api pip install -e ".[ml]"

# 录制 demo 视频（详见 doc/Demo录制脚本_5分钟.md）
demo:
	bash scripts/record_demo.sh

# 仅自动演示（不重置数据，假设你已 ready）
demo-play:
	NODE_PATH=$$(npm root -g) node scripts/demo_runner.js

# 演示 dry-run（仅打印步骤）
demo-dry:
	DEMO_DRY_RUN=1 NODE_PATH=$$(npm root -g) node scripts/demo_runner.js
