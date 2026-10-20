"""doctor leave, and notification kind, appointment and read time (reminders, rebooking offers)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-20 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = ("info", "reminder_day", "reminder_soon", "rebook", "unavailable", "turn_near")


def upgrade() -> None:
    op.create_table(
        "doctor_leave",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("end_date >= start_date", name="ck_doctor_leave_dates"),
    )
    op.create_index("ix_doctor_leave_doctor_id", "doctor_leave", ["doctor_id"])
    op.add_column("notification", sa.Column("kind", sa.String(length=16), server_default="info", nullable=False))
    op.add_column("notification", sa.Column("appointment_id", sa.Integer(), nullable=True))
    op.add_column("notification", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_notification_appointment", "notification", "appointment", ["appointment_id"], ["id"])
    op.create_check_constraint("ck_notification_kind", "notification", f"kind IN ({', '.join(repr(k) for k in KINDS)})")
    op.create_index(
        "uq_notification_reminder",
        "notification",
        ["appointment_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind IN ('reminder_day', 'reminder_soon')"),
    )
    # The analytics role reads reporting views only; nothing new is exposed to it.


def downgrade() -> None:
    op.drop_index("uq_notification_reminder", table_name="notification")
    op.drop_constraint("ck_notification_kind", "notification", type_="check")
    op.drop_constraint("fk_notification_appointment", "notification", type_="foreignkey")
    op.drop_column("notification", "read_at")
    op.drop_column("notification", "appointment_id")
    op.drop_column("notification", "kind")
    op.drop_index("ix_doctor_leave_doctor_id", table_name="doctor_leave")
    op.drop_table("doctor_leave")
