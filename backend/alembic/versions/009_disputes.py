"""disputes

Revision ID: 009_disputes
Revises: 008_attachments
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "009_disputes"
down_revision: Union[str, None] = "008_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    dispute_status = postgresql.ENUM(
        "open",
        "under_review",
        "resolved",
        "rejected",
        name="dispute_status",
        create_type=False,
    )
    dispute_resolution = postgresql.ENUM(
        "refund_client",
        "release_to_freelancer",
        "partial_refund",
        name="dispute_resolution",
        create_type=False,
    )
    dispute_status.create(bind, checkfirst=True)
    dispute_resolution.create(bind, checkfirst=True)

    if "disputes" not in inspector.get_table_names():
        op.create_table(
            "disputes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("contract_id", sa.Integer(), nullable=False),
            sa.Column("opened_by", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("status", dispute_status, nullable=False),
            sa.Column("resolution", dispute_resolution, nullable=True),
            sa.Column("resolution_notes", sa.Text(), nullable=True),
            sa.Column("partial_amount", sa.Numeric(precision=12, scale=2), nullable=True),
            sa.Column("resolved_by", sa.Integer(), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["opened_by"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_disputes_id", "disputes", ["id"])
        op.create_index("ix_disputes_contract_id", "disputes", ["contract_id"])
        op.create_index("ix_disputes_opened_by", "disputes", ["opened_by"])
        op.create_index("ix_disputes_status", "disputes", ["status"])
        op.execute(
            """
            CREATE UNIQUE INDEX uq_dispute_active_contract
            ON disputes (contract_id)
            WHERE status IN ('open'::dispute_status, 'under_review'::dispute_status)
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "disputes" in inspector.get_table_names():
        op.execute("DROP INDEX IF EXISTS uq_dispute_active_contract")
        op.drop_index("ix_disputes_status", table_name="disputes")
        op.drop_index("ix_disputes_opened_by", table_name="disputes")
        op.drop_index("ix_disputes_contract_id", table_name="disputes")
        op.drop_index("ix_disputes_id", table_name="disputes")
        op.drop_table("disputes")
    sa.Enum(name="dispute_resolution").drop(bind, checkfirst=True)
    sa.Enum(name="dispute_status").drop(bind, checkfirst=True)
