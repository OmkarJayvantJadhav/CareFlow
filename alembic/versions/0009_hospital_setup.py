"""hospital setup: the hospital's details, department search words, a doctor's last day, retired slots

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-27 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_SLOT = ("free", "booked", "blocked")
NEW_SLOT = (*OLD_SLOT, "retired")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "hospital_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", postgresql.JSONB(), nullable=False),
        sa.Column("address", sa.String(200), server_default="", nullable=False),
        sa.Column("phone", sa.String(30), server_default="", nullable=False),
        sa.Column("reception_opens", sa.Time(), nullable=False),
        sa.Column("reception_closes", sa.Time(), nullable=False),
        sa.Column("emergency_note", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_hospital_profile_single_row"),
    )
    op.add_column(
        "department",
        sa.Column("aliases", postgresql.ARRAY(sa.String(40)), server_default="{}", nullable=False),
    )
    op.add_column("doctor", sa.Column("last_day", sa.Date(), nullable=True))
    op.drop_constraint("ck_slot_status", "slot", type_="check")
    op.create_check_constraint("ck_slot_status", "slot", _in("status", NEW_SLOT))


def downgrade() -> None:
    op.execute("UPDATE slot SET status = 'blocked' WHERE status = 'retired'")
    op.drop_constraint("ck_slot_status", "slot", type_="check")
    op.create_check_constraint("ck_slot_status", "slot", _in("status", OLD_SLOT))
    op.drop_column("doctor", "last_day")
    op.drop_column("department", "aliases")
    op.drop_table("hospital_profile")
