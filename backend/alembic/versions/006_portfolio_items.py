"""portfolio items

Revision ID: 006_portfolio_items
Revises: 005_mock_milestone_payments
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_portfolio_items"
down_revision: Union[str, None] = "005_mock_milestone_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_url", sa.String(length=500), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portfolio_items_id", "portfolio_items", ["id"])
    op.create_index("ix_portfolio_items_user_id", "portfolio_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_portfolio_items_user_id", table_name="portfolio_items")
    op.drop_index("ix_portfolio_items_id", table_name="portfolio_items")
    op.drop_table("portfolio_items")
