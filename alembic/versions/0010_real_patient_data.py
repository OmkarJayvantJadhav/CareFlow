"""real patient data: name column, encrypted phone numbers with a search hash, erasure on request

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-28 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_PHONE_CHECK = "phone_masked ~ '^\\+91 [0-9]{2}X{6}[0-9]{2}$'"
NEW_PHONE_CHECK = f"{OLD_PHONE_CHECK} OR (erased_at IS NOT NULL AND phone_masked = '')"


def upgrade() -> None:
    op.alter_column("patient", "synthetic_name", new_column_name="name")
    op.add_column("patient", sa.Column("phone_encrypted", sa.Text(), nullable=True))
    op.add_column("patient", sa.Column("phone_hash", sa.String(64), nullable=True))
    op.add_column("patient", sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_patient_phone_hash", "patient", ["phone_hash"])
    op.drop_constraint("ck_patient_phone_masked", "patient", type_="check")
    op.create_check_constraint("ck_patient_phone_masked", "patient", NEW_PHONE_CHECK)


def downgrade() -> None:
    # Erased records keep their (anonymous) history; give them a placeholder the old rule accepts.
    op.execute("UPDATE patient SET phone_masked = '+91 00XXXXXX00' WHERE phone_masked = ''")
    op.drop_constraint("ck_patient_phone_masked", "patient", type_="check")
    op.create_check_constraint("ck_patient_phone_masked", "patient", OLD_PHONE_CHECK)
    op.drop_index("ix_patient_phone_hash", "patient")
    op.drop_column("patient", "erased_at")
    op.drop_column("patient", "phone_hash")
    op.drop_column("patient", "phone_encrypted")
    op.alter_column("patient", "name", new_column_name="synthetic_name")
