"""conversation and knowledge base metadata

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19 16:35:15.760485
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("history", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("pending_action", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("failed_attempts", sa.SmallInteger(), nullable=False),
        sa.Column("handoff_ticket_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("language IN ('en', 'hi', 'mr')", name="ck_conversation_language"),
        sa.ForeignKeyConstraint(
            ["handoff_ticket_id"],
            ["handoff_ticket.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_session", "conversation", ["session_id"], unique=False)
    op.create_index("ix_conversation_user", "conversation", ["user_id"], unique=False)
    # The knowledge base is rebuilt by ingestion, so existing rows can simply be cleared
    # before the new NOT NULL columns are added.
    op.execute("DELETE FROM kb_chunk")
    op.execute("DELETE FROM kb_document")
    op.add_column("kb_chunk", sa.Column("chunk_index", sa.SmallInteger(), nullable=False))
    op.add_column("kb_chunk", sa.Column("embedding_model", sa.String(length=120), nullable=False))
    op.create_index(op.f("ix_kb_chunk_embedding_model"), "kb_chunk", ["embedding_model"], unique=False)
    op.add_column("kb_document", sa.Column("doc_key", sa.String(length=200), nullable=False))
    op.add_column("kb_document", sa.Column("content_hash", sa.String(length=64), nullable=False))
    op.create_index(op.f("ix_kb_document_doc_key"), "kb_document", ["doc_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_kb_document_doc_key"), table_name="kb_document")
    op.drop_column("kb_document", "content_hash")
    op.drop_column("kb_document", "doc_key")
    op.drop_index(op.f("ix_kb_chunk_embedding_model"), table_name="kb_chunk")
    op.drop_column("kb_chunk", "embedding_model")
    op.drop_column("kb_chunk", "chunk_index")
    op.drop_index("ix_conversation_user", table_name="conversation")
    op.drop_index("ix_conversation_session", table_name="conversation")
    op.drop_table("conversation")
