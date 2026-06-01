"""Phase 1 domain tables: accounts / balance_snapshots / cash_flow_items /
instruments / credit_lines / reserve_rules + Phase 2/3 占位
(forecasts / forecast_weeks / strategy_plans / plan_actions)

Revision ID: 0002_phase1_domain
Revises: 0001_phase0_init
Create Date: 2026-05-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase1_domain"
down_revision: str | None = "0001_phase0_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False, index=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("bank_name", sa.String(length=120), nullable=True),
        sa.Column("account_number", sa.String(length=80), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("account_type", sa.String(length=20), nullable=False, server_default="basic"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "balance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("account_id", sa.String(length=36), sa.ForeignKey("accounts.id"), nullable=False, index=True),
        sa.Column("as_of_date", sa.Date(), nullable=False, index=True),
        sa.Column("balance", sa.Numeric(20, 2), nullable=False),
        sa.Column("available_balance", sa.Numeric(20, 2), nullable=False),
        sa.Column("restricted_balance", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="eod"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "cash_flow_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("account_id", sa.String(length=36), sa.ForeignKey("accounts.id"), nullable=True, index=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False, index=True),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=False, index=True),
        sa.Column("week_t", sa.Integer(), nullable=True, index=True),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("certainty_layer", sa.String(length=20), nullable=False),
        sa.Column("counterparty", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "instruments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False, index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("liquidity_tier", sa.String(length=10), nullable=True),
        sa.Column("rate", sa.Numeric(8, 6), nullable=False),
        sa.Column("tenor_options", sa.JSON(), nullable=False),
        sa.Column("min_amount", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("max_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("redeemable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("redeem_cost", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("counterparty", sa.String(length=120), nullable=True),
        sa.Column("whitelisted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("finance_priority", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "credit_lines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("instrument_id", sa.String(length=36), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("bank_name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("limit_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("used_amount", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("rate", sa.Numeric(8, 6), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "reserve_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("rule_type", sa.String(length=20), nullable=False),
        sa.Column("fixed_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("rolling_weeks", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Phase 2/3 占位
    op.create_table(
        "forecasts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("horizon_weeks", sa.Integer(), nullable=False, server_default="13"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ready"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("accuracy", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "forecast_weeks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("forecast_id", sa.String(length=36), sa.ForeignKey("forecasts.id"), nullable=False, index=True),
        sa.Column("week_t", sa.Integer(), nullable=False),
        sa.Column("scenario", sa.String(length=20), nullable=False),
        sa.Column("net_cash_flow", sa.Numeric(20, 2), nullable=False),
        sa.Column("lower_bound", sa.Numeric(20, 2), nullable=True),
        sa.Column("upper_bound", sa.Numeric(20, 2), nullable=True),
        sa.Column("layer_breakdown", sa.JSON(), nullable=True),
    )

    op.create_table(
        "strategy_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("forecast_id", sa.String(length=36), sa.ForeignKey("forecasts.id"), nullable=True),
        sa.Column("risk_knob", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="proposed"),
        sa.Column("expected_net_income", sa.Numeric(20, 2), nullable=True),
        sa.Column("safety_cushion_curve", sa.JSON(), nullable=True),
        sa.Column("gap_warning", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("high_finance_dep", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "plan_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("strategy_plans.id"), nullable=False, index=True),
        sa.Column("week_t", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("tenor_weeks", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("plan_actions")
    op.drop_table("strategy_plans")
    op.drop_table("forecast_weeks")
    op.drop_table("forecasts")
    op.drop_table("reserve_rules")
    op.drop_table("credit_lines")
    op.drop_table("instruments")
    op.drop_table("cash_flow_items")
    op.drop_table("balance_snapshots")
    op.drop_table("accounts")
