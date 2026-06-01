"""Phase 4 patch: reasoning_content on conversation_messages（DeepSeek V4 thinking mode）

Revision ID: 0004_phase4_reasoning
Revises: 0003_phase4_chat
Create Date: 2026-05-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase4_reasoning"
down_revision: str | None = "0003_phase4_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("reasoning_content", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_messages", "reasoning_content")
