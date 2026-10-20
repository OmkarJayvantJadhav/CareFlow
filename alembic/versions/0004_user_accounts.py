"""user accounts: password hash, self-registration flag, creation time

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("password_hash", sa.String(length=200), nullable=True))
    op.add_column(
        "app_user", sa.Column("self_registered", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.add_column(
        "app_user",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("app_user", "created_at")
    op.drop_column("app_user", "self_registered")
    op.drop_column("app_user", "password_hash")
