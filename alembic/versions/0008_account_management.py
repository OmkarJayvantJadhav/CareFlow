"""account management: active accounts, forced password change, sign-in invalidation, last sign-in

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-27 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.add_column(
        "app_user", sa.Column("must_change_password", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.add_column("app_user", sa.Column("credentials_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("app_user", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("app_user", "last_login_at")
    op.drop_column("app_user", "credentials_version")
    op.drop_column("app_user", "must_change_password")
    op.drop_column("app_user", "active")
