"""Initial provider-neutral document, history and ingestion lock schema."""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False, unique=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("ingestion_status", sa.String(20), nullable=False),
        sa.Column("ingestion_job_id", sa.String(128)),
        sa.Column("status_message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_index("ix_documents_ingestion_status", "documents", ["ingestion_status"])
    op.create_table(
        "question_answers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("source_references", sa.JSON, nullable=False),
        sa.Column("model_id", sa.String(512), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_question_answers_document_created", "question_answers", ["document_id", "created_at"])
    op.create_index("ix_question_answers_created_at", "question_answers", ["created_at"])
    op.create_table("ingestion_locks", sa.Column("id", sa.Integer, primary_key=True))
    op.execute(sa.text("INSERT INTO ingestion_locks (id) VALUES (1)"))


def downgrade():
    op.drop_table("question_answers")
    op.drop_table("documents")
    op.drop_table("ingestion_locks")
