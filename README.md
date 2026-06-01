# 稳盈 / Poise

> **Cash Forecasting & Liquidity Strategy Agent** — 财资人员的智能参谋
>
> 出预测与策略建议，不自动执行交易。

[![tests](https://img.shields.io/badge/pytest-39_passed-success)]() [![phase](https://img.shields.io/badge/MVP-7%2F7_phases-success)]() [![solver](https://img.shields.io/badge/MILP-PuLP%20%2B%20CBC-blue)]() [![llm](https://img.shields.io/badge/LLM-DeepSeek--V4-blueviolet)]()

## 📚 文档

- [产品需求说明书](doc/稳盈Poise_产品需求说明书.docx)
- [系统设计指导说明书](doc/稳盈Poise_系统设计指导说明书.md)
- [开发计划 V0.1](doc/稳盈Poise_开发计划_V0.1.md)
- **[用户手册](doc/用户手册.md)** —— 给财资人员
- **[运维手册](doc/运维手册.md)** —— 给运维
- **[CSV 数据契约](doc/数据契约_CSV.md)** —— 接入真实数据

## 🏗️ 仓库结构

```
apps/
  api/                       FastAPI + SQLAlchemy + Alembic + Celery + PuLP/CBC + DeepSeek
    poise/
      core/                  config / rbac / audit / celery_app
      domain/                models / schemas（15 张表）
      data_integration/      CSV importer + quality gate
      forecasting/           分层 + 双情景 + MAPE
      optimization/          MILP build_model + solve + multi_plan
      llm/                   DeepSeek client + tools + orchestrator
      feedback/              rolling + mape + bias correction
      api/v1/                33 个 REST endpoint
    tests/                   39 单测 + US-1~US-6 LLM 回归
    seeds/demo_company/      13 周完整剧情种子
  web/                       Next.js 14 + Tailwind + shadcn 风格 + ECharts
    app/(dashboard)/         8 个业务页面
    components/              通用 UI（Card / Drawer / Tabs / Textarea / DataTable / ECharts...）
doc/                         产品/设计/开发/用户/运维/CSV 契约 文档
scripts/smoke.sh             端到端冒烟脚本
docker-compose.yml           6 服务全栈
```

## ⚡ 快速开始

需要：Docker、Docker Compose、Node 20+、pnpm 9+。

```bash
# 1. 配置环境
cp .env.example .env
# 编辑 .env，至少把 DEEPSEEK_API_KEY 填上

# 2. 启动全栈
make up

# 3. 初始化数据
docker compose exec api alembic upgrade head           # 应用 5 个迁移
docker compose exec api python -m poise.scripts.bootstrap   # 创建 4 个默认用户
make seed                                              # 导入 demo 种子

# 4. 访问
#   Web   → http://localhost:3000
#   API   → http://localhost:8001/docs

# 5. 端到端冒烟（< 2 秒）
bash scripts/smoke.sh
```

默认账号：`admin / treasurer / analyst / viewer`，密码 `Poise@2026`。

常用命令见 `make help`。

## 🎯 核心闭环

```
感知 → 预测 → 推理 → 建议 → 反馈学习
 ↓     ↓      ↓      ↓        ↓
CSV   13周   MILP    3档     EMA偏差
导入  双情景  皇冠   方案    校正回流
```

| 引擎 | 核心 |
|---|---|
| **预测** | 分层（确定/规律/不确定）+ 双情景（中性/悲观）+ MinCash 滚动覆盖 |
| **决策** | PuLP MILP 多期现金调度：投/融/留 + 资金守恒 + 6 类硬约束 + 不可行松弛诊断 |
| **LLM** | DeepSeek V4 + 6 个 tool + reasoning_content 多轮支持 + 数字纪律双重设防 |
| **反馈** | 每周一 06:00 Celery Beat 滚动 + 分层 MAPE + (category, direction) EMA 校正系数 |

## 📊 性能基线（demo 数据规模）

| 操作 | 耗时 |
|---|---:|
| 13 周双情景预测 | < 20 ms |
| 三档 MILP 求解 | 80-100 ms |
| what-if 重算 | 60-80 ms |
| 滚动重跑 | < 20 ms |
| LLM 对话单轮（V4 thinking） | 7-30 s |
| **端到端冒烟（10 步）** | **< 2 s** |

## ✅ 测试

```bash
# 单测（无 LLM 依赖）
docker compose exec api pytest -q --ignore=tests/test_us_dialogues.py
# → 39 passed

# US-1~US-6 LLM 对话回归（需 DEEPSEEK_API_KEY）
docker compose exec -e DEEPSEEK_API_KEY="$(grep ^DEEPSEEK_API_KEY .env | cut -d= -f2)" \
  api pytest tests/test_us_dialogues.py -v
# → 6 passed

# 端到端冒烟
bash scripts/smoke.sh
```

## 🔐 数字纪律（命脉）

- **LLM 永远不出金额**：prompt 层禁令 + 代码层 tool 调用是金额唯一来源
- **方案采纳由人**：treasurer 角色才有 `plan.adopt` 权限
- **全程审计**：HTTP 写、LLM 调用、方案变更、滚动重跑 → AuditLog（含 actor_role）

## 🛣️ 演进路线

| 阶段 | 范围 | 状态 |
|---|---|---|
| **MVP** | 单体企业 · 参谋 · 策略最优 | ✅ 7/7 phases 完成 |
| 增强 | 集中度 / 流动性分层 / 期限错配精修；流式对话 | 留接口 |
| 集团版 | 多法人 / 资金池归集 / 上存下借 / 委托贷款 / 内部计价 | 数据模型预留 `entity_id` |
| 跨境 / 进阶 | 多币种 / 跨境额度 / 市价品种 / 风险计量 | — |

## 🧪 阶段交付

| Phase | 范围 | 测试 |
|---|---|---:|
| 0 · 基础设施 | monorepo / Docker / RBAC / Audit / CI | 7 |
| 1 · 领域模型 | 11 张核心表 + CSV 导入 + 质量门 | 8 |
| 2 · 预测引擎 | 分层 + 双情景 + MAPE 骨架 | 10 |
| 3 · MILP 决策 | 3 档 + 不可行诊断 + 影子价 | 7 |
| 3a · 演示数据 | 13 周完整剧情（US-1~US-6 全覆盖） | — |
| 4 · LLM 编排 | DeepSeek V4 + 6 个 tool + reasoning | 7 |
| 5 · 前端体验 | 8 页面 + what-if 抽屉 + 管理后台 | — |
| 6 · 反馈学习 | Celery Beat + MAPE + EMA 偏差校正 | — |
| 7 · 联调 + UAT | 冒烟脚本 + US 回归 + 文档 | 6（LLM） |

**累计**：39 单测 + 6 LLM 回归 + 1 端到端冒烟脚本。

## 📜 License

内部项目（汉得实施项目交付物）。
