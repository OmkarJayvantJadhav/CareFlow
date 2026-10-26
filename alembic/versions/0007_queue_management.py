"""queue management: doctor accounts, virtual queue, transfers, left-without-being-seen, priority rules and
clinician-authorized priority requests

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-26 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = {
    "role": ("patient", "caregiver", "staff", "admin"),
    "appointment": ("booked", "rescheduled", "cancelled", "completed", "no_show", "displaced"),
    "entry": ("waiting", "called", "in_consultation", "done", "missed", "closed"),
    "event": (
        "check_in", "walk_in", "call", "consult_start", "consult_end", "missed_turn", "return", "priority",
        "break", "resume", "delay", "emergency", "unavailable", "session_closed",
    ),
    "notification": ("info", "reminder_day", "reminder_soon", "rebook", "unavailable", "turn_near"),
}  # fmt: skip
NEW = {
    "role": (*OLD["role"], "doctor"),
    "appointment": (*OLD["appointment"], "left"),
    "entry": (*OLD["entry"], "transferred", "left"),
    "event": (*OLD["event"], "remote_join", "arrived", "transfer_out", "transfer_in", "left", "priority_request"),
    "notification": (*OLD["notification"], "transfer", "delay"),
}
CHECKS = {
    "role": ("ck_app_user_role", "app_user", "role"),
    "appointment": ("ck_appointment_status", "appointment", "status"),
    "entry": ("ck_queue_entry_status", "queue_entry", "status"),
    "event": ("ck_queue_event_type", "queue_event", "type"),
    "notification": ("ck_notification_kind", "notification", "kind"),
}
CATEGORIES = ("senior", "child", "pregnant", "disability")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _replace_checks(values: dict) -> None:
    for key, (name, table, column) in CHECKS.items():
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _in(column, values[key]))


def upgrade() -> None:
    _replace_checks(NEW)

    op.add_column("app_user", sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor.id"), nullable=True))
    op.create_check_constraint("ck_app_user_doctor_has_record", "app_user", "role <> 'doctor' OR doctor_id IS NOT NULL")

    op.add_column(
        "queue_entry", sa.Column("joined_remotely", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.add_column("queue_entry", sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "queue_entry",
        sa.Column("transferred_from_id", sa.Integer(), sa.ForeignKey("queue_entry.id"), nullable=True),
    )
    # A transferred entry hands its appointment on to the entry that replaces it.
    op.drop_constraint("uq_queue_entry_appointment", "queue_entry", type_="unique")
    op.create_index(
        "uq_queue_entry_appointment",
        "queue_entry",
        ["appointment_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'transferred'"),
    )

    rule = op.create_table(
        "priority_rule",
        sa.Column("category", sa.String(length=12), primary_key=True),
        sa.Column("weight", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_in("category", CATEGORIES), name="ck_priority_rule_category"),
        sa.CheckConstraint("weight BETWEEN 0 AND 3", name="ck_priority_rule_weight"),
    )
    op.bulk_insert(rule, [{"category": c, "weight": 0} for c in CATEGORIES])

    op.create_table(
        "priority_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_id", sa.Integer(), sa.ForeignKey("queue_entry.id"), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'declined')", name="ck_priority_request_status"),
        sa.CheckConstraint("priority BETWEEN 0 AND 3", name="ck_priority_request_priority"),
    )
    op.create_index(
        "uq_priority_request_pending",
        "priority_request",
        ["entry_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_priority_request_pending", table_name="priority_request")
    op.drop_table("priority_request")
    op.drop_table("priority_rule")
    op.drop_index("uq_queue_entry_appointment", table_name="queue_entry")
    op.create_unique_constraint("uq_queue_entry_appointment", "queue_entry", ["appointment_id"])
    op.drop_column("queue_entry", "transferred_from_id")
    op.drop_column("queue_entry", "arrived_at")
    op.drop_column("queue_entry", "joined_remotely")
    op.drop_constraint("ck_app_user_doctor_has_record", "app_user", type_="check")
    op.drop_column("app_user", "doctor_id")
    _replace_checks(OLD)
