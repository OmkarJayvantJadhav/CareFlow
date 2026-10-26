"""messages by SMS and e-mail: patient e-mail and contact choice, notification delivery, messaging setting

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-30 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("patient", sa.Column("email_masked", sa.String(120), server_default="", nullable=False))
    op.add_column("patient", sa.Column("email_encrypted", sa.Text(), nullable=True))
    op.add_column("patient", sa.Column("contact_by", sa.String(8), server_default="sms", nullable=False))
    op.create_check_constraint("ck_patient_contact_by", "patient", "contact_by IN ('sms', 'email', 'app')")
    op.add_column("notification", sa.Column("delivery", sa.String(10), nullable=True))
    op.add_column("notification", sa.Column("delivered_via", sa.String(10), nullable=True))
    op.add_column("notification", sa.Column("delivery_attempts", sa.SmallInteger(), server_default="0", nullable=False))
    op.add_column("notification", sa.Column("delivery_next_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notification", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notification", sa.Column("delivery_note", sa.String(200), nullable=True))
    op.create_check_constraint(
        "ck_notification_delivery", "notification", "delivery IN ('pending', 'sent', 'failed', 'skipped')"
    )
    op.create_index(
        "ix_notification_delivery_pending",
        "notification",
        ["id"],
        postgresql_where=sa.text("delivery = 'pending'"),
    )
    op.create_table(
        "messaging_setting",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("kinds", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(60), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_messaging_setting_single_row"),
    )


def downgrade() -> None:
    op.drop_table("messaging_setting")
    op.drop_index("ix_notification_delivery_pending", table_name="notification")
    op.drop_constraint("ck_notification_delivery", "notification", type_="check")
    for column in ("delivery_note", "delivered_at", "delivery_next_at", "delivery_attempts", "delivered_via",
                   "delivery"):  # fmt: skip
        op.drop_column("notification", column)
    op.drop_constraint("ck_patient_contact_by", "patient", type_="check")
    for column in ("contact_by", "email_encrypted", "email_masked"):
        op.drop_column("patient", column)
