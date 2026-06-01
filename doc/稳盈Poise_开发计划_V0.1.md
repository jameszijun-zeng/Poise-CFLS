# 稳盈 / Poise · MVP 开发计划（V0.1）

> 本文为 2026-05-29 与团队共同确认的开发基线，从 `~/.claude/plans/` 复制到项目 `doc/` 持久化。后续若需更新版本，请新增 V0.2 / V0.3 并保留历史。

## Context

当前仓库（`Poise-CFLS/`）除 `doc/` 内两份说明书外尚无任何代码，是绿地项目。两份文档已经把"做什么 / 为什么 / 架构原则"讲得很清楚：

- **核心闭环**：感知 → 预测 → 推理 → 建议 → 反馈学习
- **架构皇冠**：13 周 MILP 多期现金调度（PuLP/HiGHS），LLM 只做意图翻译、工具编排与解释生成，**绝不出数字**
- **MVP 边界**：单体企业、单一法人；不执行交易；预留集团扩展点

本计划目标：在已确认的工程约束下（Python 后端 + Next.js 前端、CSV 种子数据起步、DeepSeek-V4、试点可用版含 RBAC 与审计 UI），把"预测 + 求解 + 对话解释 + 滚动反馈"端到端跑通，达到可在 10–20 人小范围试点使用的程度。

**预算估算**：单人全栈 ≈ 9–11 周；2 人并行 ≈ 5–6 周。

---

## 1. 工程基线（已确认）

| 维度 | 选择 | 理由 |
|---|---|---|
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.x + Alembic + Pydantic v2 | 与 OR-Tools/PuLP/pandas/LLM SDK 原生融合；ASGI 性能足够 |
| 求解器 | PuLP 建模 + **HiGHS（默认，highspy）** / CBC 兜底 | 单纯形与 MIP 性能优于 CBC；MIT 协议；商用 Gurobi 留接口 |
| 数据库 | PostgreSQL 16（Docker Compose 本地） | 事务、JSON 字段、可演进至生产；Alembic 管迁移 |
| 任务队列 | **Celery + Redis** | 滚动重跑、求解异步化、预警推送；为后续多租户/规模扩展留路 |
| 前端 | Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui | 试点版需精致 UI；shadcn 在审计/RBAC 后台与对话 UI 都顺手 |
| 图表 | **Apache ECharts**（13 周曲线 / 安全垫 / 方案对比 / 桑基图） | 中文金融场景生态成熟；交互能力强；支持复杂叠加图 |
| 对话流 | Vercel AI SDK（前端流式） + **DeepSeek function calling**（OpenAI 兼容协议） | DeepSeek API 与 OpenAI SDK 兼容，仅换 `base_url`+`api_key` |
| 鉴权 | NextAuth.js（前端） + JWT（API） + RBAC 装饰器 | 10–20 人试点必需；与 FastAPI 中间件天然分层 |
| LLM | **DeepSeek-V4（解释/编排） / DeepSeek-V4-Lite（tool 路由）** | 中文场景强；OpenAI 兼容协议；成本远低于 GPT-4o |
| 数据接入 | CSV/JSON 种子导入脚本 + 后台手工录入 UI | 聚焦核心引擎验证；ERP/银企适配器留 P1 |
| 部署 | Docker Compose 一键启动（api + web + postgres + redis + celery-worker + celery-beat） | 试点期单机即可；后续可上 K8s |

---

## 2. 仓库结构

```
Poise-CFLS/
├── doc/                              # 既有产品/系统文档 + 开发计划
├── apps/
│   ├── api/                          # FastAPI 后端
│   │   ├── poise/
│   │   │   ├── main.py
│   │   │   ├── core/                 # 配置、依赖、JWT、RBAC、AuditLog 中间件
│   │   │   ├── domain/               # SQLAlchemy 实体 + Pydantic schema
│   │   │   ├── data_integration/     # 适配器接口 + CSV/JSON 导入器 + 质量门
│   │   │   ├── forecasting/          # 分层预测：deterministic/pattern/uncertain + 双情景
│   │   │   ├── optimization/         # MILP 建模与求解
│   │   │   ├── llm/                  # DeepSeek 编排：tools / orchestrator / prompts
│   │   │   ├── feedback/             # 偏差回流 + 采纳/否决
│   │   │   └── api/                  # REST 路由（v1）
│   │   ├── tests/  ├── alembic/  ├── seeds/  └── pyproject.toml
│   └── web/                          # Next.js 前端
│       ├── app/
│       │   ├── (auth)/login/
│       │   └── (dashboard)/{chat,forecast,plans,alerts,data,admin,accuracy}/
│       ├── components/  └── lib/
├── packages/shared/                  # OpenAPI 生成的 TS 类型 + 公共契约
├── docker-compose.yml
└── .github/workflows/                # lint / type / test CI
```

---

## 3. 阶段拆分（MVP）

### Phase 0 · 基础设施（≈ 1 周）

**目标**：仓库可一键启动；登录、RBAC、AuditLog、健康检查、CI 跑通。

关键交付：
- monorepo 骨架（pnpm workspaces + Poetry/uv）
- `docker-compose.yml`：postgres + redis + api + web + celery-worker + celery-beat
- 后端：FastAPI + SQLAlchemy + Alembic 初始化；JWT 登录；RBAC 装饰器（roles：admin/treasurer/analyst/viewer）；`AuditLog` 中间件（拦截每次写操作与 LLM 调用）
- Celery 骨架：默认队列 + `optimize` 重队列 + `beat` 定时器；任务结果回 Postgres
- 前端：Next.js + NextAuth；登录页；空 Dashboard 框架；shadcn/ui 主题
- CI：ruff + mypy + pytest（API） / eslint + tsc + vitest（web）

### Phase 1 · 领域模型 + 种子数据（≈ 1.5 周）

**目标**：系统设计文档 §2 的核心实体全部落库；提供 CSV 导入与手工 UI。

关键交付：
- SQLAlchemy 模型：`Entity / Account / BalanceSnapshot / CashFlowItem / Instrument / CreditLine / ReserveRule / Forecast / StrategyPlan / PlanAction / AuditLog`（每张表保留 `entity_id` 钩子）
- Pydantic schema（与 OpenAPI 自动同步到前端类型）
- 数据质量门：完整性、异常值（金额量级）、币种、日期→周次归集
- CSV/JSON 导入器（命令行 + Web 上传）
- 后台录入 UI：现金流项、品种、授信、备付规则

### Phase 3a · 合成演示数据集（与 Phase 1 并行，≈ 0.5 周）

**目标**：交付一份"虚拟单体企业 13 周完整剧情"的种子数据，让需求文档 US-1~US-6 全部能在 demo 中复现。

剧情设计：
- **企业画像**：制造/贸易型单体企业，年营收 ~10 亿，月度回款节奏明显
- **账户**：3 个银行账户（基本户/一般户/外币户简化为人民币）
- **现金流项**：13 周覆盖销售回款、采购付款、薪酬、税费、利息、还本、租金；混合 deterministic / pattern / uncertain 三层
- **品种白名单**（对齐需求文档 §5.3.4）：
  - 活钱层：货币基金、协定存款、隔夜逆回购
  - 稳健层：通知存款、7/14/28 天定存、现金管理理财
  - 增益层：3/6 月定存、大额存单、结构性存款
- **融资工具**：流贷额度、票据贴现、银行承兑（按成本升序）
- **剧情埋点**：
  - W3 一笔大额并购付款（呼应 US-3 缺口场景）
  - W6 某大客户回款延后（呼应 US-5 what-if）
  - W9 起进入收入不确定区间（呼应 US-1 区间预测）
  - 悲观情景下 W11 触发缺口预警（呼应 US-6 主动告警）

### Phase 2 · 预测引擎（≈ 1.5 周）

**目标**：分层 + 双情景预测可用；预测产物落库；MAPE 看板可呈现。

- 分层路由：确定层（W1–4，规则）/ 规律层（W5–8，账龄 + ETS 季节性）/ 不确定层（W9–13，区间）
- 双情景：neutral（期望值）+ pessimistic（收入打折/支出从紧）
- `forecast(entity_id, as_of, horizon=13)` 内部接口
- MAPE 看板（按分层、按收支类）

### Phase 3 · 决策引擎 MILP（≈ 1.5–2 周，皇冠模块）

**目标**：系统设计文档 §3 的完整 MILP 可解，多 riskKnob 多方案，缺口诊断可读。

- PuLP 建模 + HiGHS 求解
- 决策变量：`x[i,t,d], y[f,t], red[i,t], B[t]` + 整数 `z[i,t,d]`（最小起投）
- 硬约束 C1–C6 全部上线；软约束 C7–C9 留接口
- 目标函数：投资利息 − 融资成本 − 赎回成本
- 多方案：`riskKnob ∈ {稳健, 折中, 进取}` 三次求解
- 悲观情景缺口预警 + 融资依赖度标签
- 不可行诊断：松弛变量 `slack[t]` + 最小化 `Σ slack[t]` 内建
- 返回最优解 + 对偶/影子价

### Phase 4 · LLM 编排层（≈ 1 周）

**目标**：6 个 tool 可被 DeepSeek function calling 正确触发；US-1~US-6 对话流跑通。

- DeepSeek 客户端封装（OpenAI SDK + `base_url=https://api.deepseek.com`）
- Tool：`run_forecast / build_and_solve / explain_plan / diagnose_infeasible / apply_overrides / query_position`
- 中文系统 prompt，明确禁止 LLM 出金额
- 分层路由：lite 跑 tool 选择，V4 跑解释/诊断
- 对话历史 + AuditLog
- US-1~US-6 对话脚本回归集

### Phase 5 · 前端体验（≈ 1.5–2 周）

- **对话页**：流式聊天 UI（Vercel AI SDK）+ 下钻 tool 调用与 plan_id
- **13 周看板**：双情景曲线 + 安全垫 + 备付带 + 缺口标签
- **方案对比**：3 套方案卡片并排 + PlanAction 明细
- **what-if 沙盘**：右侧抽屉调参 → 重算对比
- **预警中心**：缺口预警 + 高融资依赖标签
- **管理后台**：用户/角色/权限、审计日志检索
- **MAPE 看板**

### Phase 6 · 反馈学习闭环（≈ 0.5–1 周）

- Celery Beat 每周一 06:00 触发（可手动）：锁定上周实际 → 计算偏差 → 更新 MAPE → 重新预测 → 重新求解
- 系统性偏差校正系数
- 方案采纳/否决记录；采纳率埋点
- "上次建议 vs 实际 vs 下一轮"对照视图

### Phase 7 · 联调、性能、UAT（≈ 1 周）

- 端到端冒烟：登录 → 导入 → 预测 → 求解 → 对话 → what-if → 采纳 → 滚动
- 性能：13 周模型 < 2s（HiGHS）；对话首 token < 2s
- US-1~US-6 回归通过
- 用户手册 + 运维手册 + 数据契约 README

---

## 4. 关键工程纪律（命脉级）

1. **LLM 与求解器边界纪律**：prompt + 代码双重设防，`explain_plan` 中金额由后端注入而非 LLM 生成
2. **MILP 不可行是常态**：松弛诊断从 Phase 3 起内建，不能后补
3. **悲观情景从简**：规则起步（回款 ×0.8 / 支出 ×1.1），留替换接口
4. **RBAC + Audit 从 Phase 0 起**：试点版必需，后补代价巨大
5. **数据质量门**：脏数据让引擎产出无意义，CSV 路径强校验
6. **DeepSeek 成本与稳定性**：`deepseek-lite` 跑 tool 路由 + `deepseek-chat`(V4) 跑解释；启用 prompt caching；保留 OpenAI/Azure 客户端开关作为热备
7. **集团演进钩子**：`entity_id` 全留；MILP 建模层留 `entities: list` 参数；动作类别注册表
8. **Celery 边界纪律**：HTTP 触发即返回 `task_id`，前端轮询/SSE 拿结果；LLM tool 调用 `build_and_solve` 默认同步等待，仅滚动重跑走异步
9. **RBAC 角色**：`admin` / `treasurer`（可采纳方案）/ `analyst`（可问可调不可采纳）/ `viewer`（只读）

---

## 5. 验证策略

| 层级 | 方式 |
|---|---|
| 单元 | pytest：预测分层、MILP 现金守恒、约束生效、不可行松弛、LLM tool schema |
| 集成 | 端到端：种子 → 预测 → 求解 → API 输出比对快照 |
| 引擎正确性 | 5 套合成场景（全闲置/全缺口/锁定冲突/授信极限/混合）人工校验 |
| LLM 对话 | US-1~US-6 6 条脚本回归；金额是否始终来自 `solve` |
| 性能 | 13 周 × 30 品种 × 5 期限 求解 < 2s（HiGHS） |
| UI/UX | 试点用户走查 + 内部 UAT |

---

## 6. 6 点决议（已确认 ✅）

| # | 决议项 | 取定 |
|---|---|---|
| 1 | 求解器默认 | **HiGHS**（highspy，CBC 兜底） |
| 2 | 异步队列 | **Celery + Redis**（含 Beat 定时任务） |
| 3 | 前端图表 | **Apache ECharts** |
| 4 | 试点用户规模 | **10–20 人** → 4 个 RBAC 角色（admin / treasurer / analyst / viewer） |
| 5 | LLM 服务 | **DeepSeek-V4**（OpenAI 兼容协议，OpenAI/Azure 客户端开关保留） |
| 6 | 演示数据 | **由本计划交付**：Phase 3a 合成"虚拟单体企业 13 周完整剧情" |

---

## 7. 计划总览

| 阶段 | 时长 | 关键产出 |
|---|---:|---|
| Phase 0 · 基础设施 | 1 周 | monorepo / Docker Compose / FastAPI 骨架 / NextAuth / RBAC / AuditLog / Celery 骨架 / CI |
| Phase 1 · 领域模型 + 种子 | 1.5 周 | 11 张核心表 / 质量门 / CSV 导入 / 后台 UI |
| Phase 3a · 合成演示数据 | 0.5 周（并行） | demo_company 13 周剧情数据 + README |
| Phase 2 · 预测引擎 | 1.5 周 | 分层 + 双情景 + MAPE 看板 |
| Phase 3 · MILP 决策引擎 | 1.5–2 周 | PuLP+HiGHS / 多方案 / 不可行松弛 / 影子价 |
| Phase 4 · LLM 编排 | 1 周 | DeepSeek-V4 + 6 个 tool + US-1~US-6 对话回归 |
| Phase 5 · 前端体验 | 1.5–2 周 | 对话 / 看板 / 方案对比 / what-if / 预警 / 管理后台 |
| Phase 6 · 反馈学习 | 0.5–1 周 | Celery Beat 滚动 + 偏差回流 + 采纳记录 |
| Phase 7 · 联调 + UAT | 1 周 | 端到端冒烟 + 性能 + 用户走查 |
| **合计** | **≈ 9–11 周（单人）** | 试点可用 MVP |
