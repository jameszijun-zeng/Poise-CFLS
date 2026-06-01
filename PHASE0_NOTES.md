# Phase 0 · 基础设施 · 交付说明

## 完成范围

✅ **仓库骨架**：`apps/api` + `apps/web` + `packages/shared`（占位）+ pnpm workspace
✅ **Docker Compose**：postgres + redis + api + web + celery-worker + celery-beat
✅ **后端 FastAPI**：
- 配置中心 (pydantic-settings)，DeepSeek/OpenAI 双客户端开关
- SQLAlchemy 2.x + Alembic（首迁移：entities / users / audit_logs）
- JWT 鉴权 + bcrypt 密码哈希
- **RBAC 装饰器**：4 个角色（admin / treasurer / analyst / viewer）+ 8 项权限矩阵
- **AuditLog 中间件**：自动拦截所有 HTTP 写操作并落库
- Celery 应用 + Beat 调度（每周一 06:00 滚动任务占位）
- `/api/v1/health` / `/api/v1/auth/login` / `/api/v1/me`
- Bootstrap CLI：`python -m poise.scripts.bootstrap` 创建 4 个默认用户
- pytest 覆盖 security + RBAC

✅ **前端 Next.js 14**：
- App Router + TypeScript + Tailwind + 内置 shadcn 风格组件（Button / Input / Card）
- NextAuth.js Credentials Provider 桥接 FastAPI 登录
- 中间件保护 dashboard 路由
- 登录页 + 概览页（拉 health + 显示当前用户）
- 8 个导航占位页（chat / forecast / plans / alerts / data / accuracy / admin）

✅ **CI**：GitHub Actions（api 跑 ruff/mypy/pytest，web 跑 typecheck/lint）

## 启动方式

```bash
cp .env.example .env
# 编辑 .env（开发期可用默认值）
make up                  # 启动全栈
make migrate             # 应用迁移（容器内）
docker compose exec api python -m poise.scripts.bootstrap
                         # 创建 4 个默认用户
```

打开：
- API 文档 → http://localhost:8000/docs
- Web 登录 → http://localhost:3000/login
- 默认账号：`admin` / `treasurer` / `analyst` / `viewer`，密码 `Poise@2026`

## 已实现的关键纪律

- **RBAC 矩阵集中在 `poise/core/rbac.py`**：业务路由用 `Depends(require("plan.adopt"))` 装饰，权限变化只改一处
- **AuditLog 通用入口**：HTTP 中间件自动捕获；业务事件（LLM 调用、方案采纳）用 `core.audit.record_event()` 显式记录
- **DeepSeek/OpenAI 双客户端开关**：`LLM_PROVIDER=deepseek|openai`，配置层留好抽象，Phase 4 实现 client 后即可切换
- **Solver 后端开关**：`SOLVER_BACKEND=highs|cbc`，Phase 3 通过 PuLP 工厂选择
- **Celery 队列分离**：`default` 走轻任务，`optimize` 重队列专跑 MILP 滚动重跑

## 下一步（Phase 1）

- 系统设计 §2 的全部业务表（CashFlowItem / Instrument / CreditLine / ReserveRule / Forecast / StrategyPlan / PlanAction / BalanceSnapshot / Account）
- CSV/JSON 导入器 + 数据质量门
- 数据录入 UI

与 Phase 1 并行的 **Phase 3a 合成演示数据集**（demo_company 13 周完整剧情）。
