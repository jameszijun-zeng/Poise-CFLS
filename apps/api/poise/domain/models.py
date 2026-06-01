"""SQLAlchemy 实体模型 · 对齐《系统设计指导说明书》§2。

每张表都带 `entity_id` 钩子，MVP 单值；未来集团演进无需结构改动。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poise.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# =====================================================================
# Phase 0：主体 / 用户 / 审计
# =====================================================================


class Entity(Base):
    """法人主体（MVP 单值，集团扩展点）。"""

    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), default="CNY")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    users: Mapped[list[User]] = relationship(back_populates="entity")
    accounts: Mapped[list[Account]] = relationship(back_populates="entity")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    entity: Mapped[Entity] = relationship(back_populates="users")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# =====================================================================
# Phase 1：账户 / 余额 / 现金流 / 投融资品种 / 授信 / 备付
# =====================================================================


class Account(Base):
    """银行账户（基本户/一般户/外币户等）。"""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    account_type: Mapped[str] = mapped_column(String(20), default="basic")  # basic/general/special
    is_active: Mapped[bool] = mapped_column(default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    entity: Mapped[Entity] = relationship(back_populates="accounts")
    balances: Mapped[list[BalanceSnapshot]] = relationship(back_populates="account")


class BalanceSnapshot(Base):
    """余额快照（实时 / 日终）。"""

    __tablename__ = "balance_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id"), nullable=False, index=True
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    available_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    restricted_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    source: Mapped[str] = mapped_column(String(20), default="eod")  # real_time / eod
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account: Mapped[Account] = relationship(back_populates="balances")


class CashFlowItem(Base):
    """现金流项 —— 预测的原子。"""

    __tablename__ = "cash_flow_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("accounts.id"), nullable=True, index=True
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # inflow / outflow
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # 销售回款 sales_collection / 采购付款 purchase_payment / 薪酬 payroll /
    # 税费 tax / 利息 interest / 还本 principal_repay / 租金 rent / 其他 other
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # contract / ar / ap / order / schedule / statistical
    expected_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    week_t: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # 1-13
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    certainty_layer: Mapped[str] = mapped_column(String(20), nullable=False)
    # deterministic / pattern / uncertain
    counterparty: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Instrument(Base):
    """投融资品种主数据 —— 策略动作的原子。"""

    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # invest / finance
    liquidity_tier: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # cash / stable / yield —— 仅投资
    rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)  # 年化
    tenor_options: Mapped[list[int]] = mapped_column(JSON, nullable=False)  # 周
    min_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    redeemable: Mapped[bool] = mapped_column(Boolean, default=True)
    redeem_cost: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal(0))
    counterparty: Mapped[str | None] = mapped_column(String(120), nullable=True)
    whitelisted: Mapped[bool] = mapped_column(Boolean, default=True)
    finance_priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CreditLine(Base):
    """授信额度。"""

    __tablename__ = "credit_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    instrument_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("instruments.id"), nullable=True
    )
    bank_name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    used_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))
    rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def available_amount(self) -> Decimal:
        return self.limit_amount - self.used_amount


class ReserveRule(Base):
    """备付金规则。MVP 推荐 rolling_coverage：最低备付 = 未来 N 周刚性支出之和。"""

    __tablename__ = "reserve_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # fixed / rolling_coverage
    fixed_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    rolling_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =====================================================================
# Phase 2/3 占位：预测结果 / 策略方案 / 方案动作
# (此处仅落地 schema，让外键关系可建立；具体生成逻辑在后续阶段实现)
# =====================================================================


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_weeks: Mapped[int] = mapped_column(Integer, default=13)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    accuracy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    weeks: Mapped[list[ForecastWeek]] = relationship(
        back_populates="forecast", cascade="all, delete-orphan"
    )


class ForecastWeek(Base):
    __tablename__ = "forecast_weeks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    forecast_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("forecasts.id"), nullable=False, index=True
    )
    week_t: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario: Mapped[str] = mapped_column(String(20), nullable=False)
    # neutral / pessimistic
    net_cash_flow: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    layer_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    forecast: Mapped[Forecast] = relationship(back_populates="weeks")


class StrategyPlan(Base):
    __tablename__ = "strategy_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    forecast_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("forecasts.id"), nullable=True
    )
    risk_knob: Mapped[str] = mapped_column(String(20), nullable=False)
    # conservative / balanced / aggressive
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    # draft / proposed / adopted / rejected
    expected_net_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    safety_cushion_curve: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    gap_warning: Mapped[bool] = mapped_column(Boolean, default=False)
    high_finance_dep: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    actions: Mapped[list[PlanAction]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PlanAction(Base):
    __tablename__ = "plan_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("strategy_plans.id"), nullable=False, index=True
    )
    week_t: Mapped[int] = mapped_column(Integer, nullable=False)
    instrument_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("instruments.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # invest / redeem / draw / repay
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    tenor_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[StrategyPlan] = relationship(back_populates="actions")


# =====================================================================
# Phase 4：对话历史
# =====================================================================


class Conversation(Base):
    """一次对话会话（多轮 message 的容器）。"""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationMessage.id"
    )


# =====================================================================
# Phase 6：反馈学习闭环（实际值 / 偏差校正 / 滚动重跑记录）
# =====================================================================


class ActualCashFlow(Base):
    """某周次实际发生的现金流聚合（按 category × direction × certainty_layer）。

    每次滚动重跑会把"上一周"的实际值快照入库，用于与 forecast 对照计算 MAPE。
    """

    __tablename__ = "actual_cash_flows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    certainty_layer: Mapped[str] = mapped_column(String(20), nullable=False)
    forecast_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="synthetic")
    # synthetic / manual / bank_feed
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BiasCorrection(Base):
    """按 (category, direction) 维度学到的系统性偏差校正系数。

    forecast_corrected = forecast_raw * multiplier
    multiplier 通过 EMA 平滑更新，避免单周抖动。
    """

    __tablename__ = "bias_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal(1))
    samples: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RollingRun(Base):
    """每次滚动重跑的记录。"""

    __tablename__ = "rolling_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False, index=True
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    triggered_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # user_id or 'scheduler'
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    forecast_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    mape_by_layer: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    mape_by_category: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    bias_updates: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConversationMessage(Base):
    """单条消息：user / assistant / tool。

    每次工具调用 + 工具返回各落一条，便于回放与审计。
    """

    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # user / assistant / tool / system
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # DeepSeek V4 thinking 模式产出的推理过程；多轮对话需原样传回 API
    reasoning_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tool_args: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tool_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # 模型与 token 计数（用于成本观测）
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
