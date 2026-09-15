"""attachments

Revision ID: 008_attachments
Revises: 007_notifications
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "008_attachments"
down_revision: Union[str, None] = "007_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "attachments" not in inspector.get_table_names():
        op.create_table(
            "attachments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("uploader_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("contract_id", sa.Integer(), nullable=True),
            sa.Column("conversation_id", sa.Integer(), nullable=True),
            sa.Column("milestone_id", sa.Integer(), nullable=True),
            sa.Column("filename", sa.String(length=200), nullable=False),
            sa.Column("storage_key", sa.String(length=500), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["uploader_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["milestone_id"], ["milestones.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("storage_key"),
        )
    indexes = {index["name"] for index in inspector.get_indexes("attachments")}
    for name, columns in (
        ("ix_attachments_id", ["id"]),
        ("ix_attachments_uploader_id", ["uploader_id"]),
        ("ix_attachments_project_id", ["project_id"]),
        ("ix_attachments_contract_id", ["contract_id"]),
        ("ix_attachments_conversation_id", ["conversation_id"]),
        ("ix_attachments_milestone_id", ["milestone_id"]),
    ):
        if name not in indexes:
            op.create_index(name, "attachments", columns)


def downgrade() -> None:
    op.drop_index("ix_attachments_milestone_id", table_name="attachments")
    op.drop_index("ix_attachments_conversation_id", table_name="attachments")
    op.drop_index("ix_attachments_contract_id", table_name="attachments")
    op.drop_index("ix_attachments_project_id", table_name="attachments")
    op.drop_index("ix_attachments_uploader_id", table_name="attachments")
    op.drop_index("ix_attachments_id", table_name="attachments")
    op.drop_table("attachments")
