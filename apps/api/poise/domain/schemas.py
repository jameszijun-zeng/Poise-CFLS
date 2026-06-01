"""Pydantic schemas（API 输入/输出契约 → OpenAPI → 前端 TS 类型）。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from poise.core.rbac import Role


# ----- Phase 0：通用 -----


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    display_name: str
    role: Role
    entity_id: str
    is_active: bool
    created_at: datetime


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    db: str = Field(description="db connectivity: ok | down")


# ----- Phase 1：领域读模型 -----


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    code: str
    base_currency: str


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_id: str
    code: str
    name: str
    bank_name: str | None
    account_number: str | None
    currency: str
    account_type: str
    is_active: bool


class BalanceSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: str
    as_of_date: date
    balance: Decimal
    available_balance: Decimal
    restricted_balance: Decimal
    currency: str
    source: str


class CashFlowItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_id: str
    account_id: str | None
    direction: str
    category: str
    source_type: str
    expected_date: date
    week_t: int | None
    amount: Decimal
    currency: str
    certainty_layer: str
    counterparty: str | None
    notes: str | None


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_id: str
    code: str
    name: str
    kind: str
    liquidity_tier: str | None
    rate: Decimal
    tenor_options: list[int]
    min_amount: Decimal
    max_amount: Decimal | None
    redeemable: bool
    redeem_cost: Decimal
    counterparty: str | None
    whitelisted: bool
    finance_priority: int | None
    currency: str


class CreditLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_id: str
    bank_name: str
    code: str
    limit_amount: Decimal
    used_amount: Decimal
    available_amount: Decimal
    rate: Decimal
    expires_at: date | None


class ReserveRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_id: str
    rule_type: str
    fixed_value: Decimal | None
    rolling_weeks: int | None


# ----- 数据质量门反馈 -----


class ImportIssue(BaseModel):
    severity: str  # error / warning
    table: str
    row: int | None = None
    field: str | None = None
    message: str


class ImportSummary(BaseModel):
    """单次 CSV/JSON 导入结果。"""

    imported: dict[str, int] = Field(default_factory=dict, description="表名 → 新增条数")
    skipped: dict[str, int] = Field(default_factory=dict, description="表名 → 跳过条数")
    issues: list[ImportIssue] = Field(default_factory=list)
    ok: bool = True


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    occurred_at: datetime
    actor_user_id: str | None
    actor_role: str | None
    event_type: str
    method: str | None
    path: str | None
    status_code: int | None
    duration_ms: int | None
    payload: dict[str, Any] | None
    notes: str | None


# ----- Phase 2：预测引擎 -----


class ForecastRunRequest(BaseModel):
    entity_id: str | None = None  # 缺省取唯一 entity
    as_of: date | None = None
    horizon_weeks: int = Field(13, ge=1, le=52)


class ForecastWeekOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    week_t: int
    scenario: str
    net_cash_flow: Decimal
    lower_bound: Decimal | None
    upper_bound: Decimal | None
    layer_breakdown: dict[str, Any] | None


class ForecastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_id: str
    as_of_date: date
    horizon_weeks: int
    status: str
    payload: dict[str, Any] | None
    created_at: datetime


class ForecastFullOut(ForecastOut):
    """带分周明细的完整预测视图。"""

    weeks: list[ForecastWeekOut] = Field(default_factory=list)


class AccuracyOut(BaseModel):
    by_layer: list[dict[str, Any]]
    by_category: list[dict[str, Any]]
    note: str | None = None


# ----- Phase 3：决策引擎 -----


class PlanActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    week_t: int
    instrument_id: str | None
    action: str
    amount: Decimal
    tenor_weeks: int | None
    notes: str | None


class StrategyPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_id: str
    forecast_id: str | None
    risk_knob: str
    status: str
    expected_net_income: Decimal | None
    safety_cushion_curve: list[Any] | None
    gap_warning: bool
    high_finance_dep: bool
    summary: str | None
    payload: dict[str, Any] | None
    created_at: datetime


class StrategyPlanFullOut(StrategyPlanOut):
    actions: list[PlanActionOut] = Field(default_factory=list)


class BuildAndSolveRequest(BaseModel):
    forecast_id: str | None = None  # 缺省取 latest
    locks: dict[int, Decimal] | None = None


class BuildAndSolveResponse(BaseModel):
    forecast_id: str
    plan_ids: list[str]
    candidates: list[StrategyPlanFullOut]
    infeasibility: dict[str, Any] | None = None


class PlanAdoptRequest(BaseModel):
    notes: str | None = None


# ----- Phase 4：对话 -----


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_id: str
    user_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conversation_id: str
    role: str
    content: str | None
    reasoning_content: str | None = None
    tool_call_id: str | None
    tool_name: str | None
    tool_args: dict[str, Any] | None
    tool_result: dict[str, Any] | None
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    created_at: datetime


class ConversationFullOut(ConversationOut):
    messages: list[ConversationMessageOut] = Field(default_factory=list)


class ChatTurnRequest(BaseModel):
    conversation_id: str | None = None  # 缺省则新建会话
    message: str
    title_hint: str | None = None  # 新会话时用作标题


class ChatTurnResponse(BaseModel):
    conversation_id: str
    assistant_text: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tokens_in: int
    tokens_out: int
    elapsed_ms: int
    model: str | None
