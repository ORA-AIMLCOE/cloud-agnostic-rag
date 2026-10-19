"""Versioned pre-ingested knowledge and atomic active-source selection."""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_releases",
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("demo_data", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "active_knowledge",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("knowledge_releases.document_id", ondelete="RESTRICT"), nullable=False),
    )


def downgrade():
    op.drop_table("active_knowledge")
    op.drop_table("knowledge_releases")
