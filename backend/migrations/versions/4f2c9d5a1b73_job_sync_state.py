"""job sync state

Revision ID: 4f2c9d5a1b73
Revises: 3128b08bc7a4
Create Date: 2026-11-12 05:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f2c9d5a1b73"
down_revision: str | None = "3128b08bc7a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_sync_state",
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source"),
    )


def downgrade() -> None:
    op.drop_table("job_sync_state")
