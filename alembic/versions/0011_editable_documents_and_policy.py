"""editable knowledge base and policy numbers: document templates, origin, hidden, edited; policy settings

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-29 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("kb_document", sa.Column("template", sa.Text(), nullable=True))
    op.add_column("kb_document", sa.Column("origin", sa.String(10), server_default="template", nullable=False))
    op.add_column("kb_document", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("kb_document", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("kb_document", sa.Column("edited_by", sa.String(60), nullable=True))
    op.add_column(
        "kb_document",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_check_constraint("ck_kb_document_origin", "kb_document", "origin IN ('template', 'edited', 'added')")
    op.create_table(
        "policy_setting",
        sa.Column("key", sa.String(40), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(60), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("policy_setting")
    # Documents added by admins exist only in the database; they go with the columns that describe them.
    op.execute("DELETE FROM kb_document WHERE origin = 'added'")
    op.drop_constraint("ck_kb_document_origin", "kb_document", type_="check")
    for column in ("updated_at", "edited_by", "edited_at", "hidden_at", "origin", "template"):
        op.drop_column("kb_document", column)
