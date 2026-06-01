"""Phase 6 feedback: actual_cash_flows / bias_corrections / rolling_runs

Revision ID: 0005_phase6_feedback
Revises: 0004_phase4_reasoning
Create Date: 2026-05-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_phase6_feedback"
down_revision: str | None = "0004_phase4_reasoning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "actual_cash_flows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("week_start", sa.Date(), nullable=False, index=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("certainty_layer", sa.String(length=20), nullable=False),
        sa.Column("forecast_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("actual_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="synthetic"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "bias_corrections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("multiplier", sa.Numeric(8, 6), nullable=False, server_default="1"),
        sa.Column("samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "rolling_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("triggered_by", sa.String(length=36), nullable=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
        sa.Column("forecast_id", sa.String(length=36), nullable=True),
        sa.Column("mape_by_layer", sa.JSON(), nullable=True),
        sa.Column("mape_by_category", sa.JSON(), nullable=True),
        sa.Column("bias_updates", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("rolling_runs")
    op.drop_table("bias_corrections")
    op.drop_table("actual_cash_flows")
