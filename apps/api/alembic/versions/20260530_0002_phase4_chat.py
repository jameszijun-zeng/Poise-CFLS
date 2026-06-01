"""Phase 4 chat: conversations + conversation_messages

Revision ID: 0003_phase4_chat
Revises: 0002_phase1_domain
Create Date: 2026-05-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase4_chat"
down_revision: str | None = "0002_phase1_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=36), sa.ForeignKey("entities.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("conversations.id"), nullable=False, index=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_call_id", sa.String(length=80), nullable=True),
        sa.Column("tool_name", sa.String(length=60), nullable=True),
        sa.Column("tool_args", sa.JSON(), nullable=True),
        sa.Column("tool_result", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(length=60), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
