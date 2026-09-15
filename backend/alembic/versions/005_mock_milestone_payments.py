"""drop stripe payment columns; keep mock milestone payments

Revision ID: 005_mock_milestone_payments
Revises: 004_reviews
Create Date: 2026-09-14

Stripe is not used. milestone_id and released_at stay so a Payment can
represent a contract payment or a milestone payment.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "005_mock_milestone_payments"
down_revision: Union[str, None] = "004_reviews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("payments")}

    # Existing contract payments keep milestone_id null. Add the link only if missing.
    if "milestone_id" not in columns:
        op.add_column("payments", sa.Column("milestone_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_payments_milestone_id",
            "payments",
            "milestones",
            ["milestone_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index("ix_payments_milestone_id", "payments", ["milestone_id"])

    if "released_at" not in columns:
        op.add_column("payments", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))

    # Leftover Stripe rows must not remain on a method the app no longer recognizes.
    op.execute(
        "UPDATE payments SET payment_method = 'mock_card' "
        "WHERE payment_method::text = 'stripe'"
    )

    indexes = {index["name"] for index in inspector.get_indexes("payments")}
    if "ix_payments_stripe_session_id" in indexes:
        op.drop_index("ix_payments_stripe_session_id", table_name="payments")
    if "ix_payments_stripe_payment_intent_id" in indexes:
        op.drop_index("ix_payments_stripe_payment_intent_id", table_name="payments")

    columns = {column["name"] for column in inspect(bind).get_columns("payments")}
    if "stripe_session_id" in columns:
        op.drop_column("payments", "stripe_session_id")
    if "stripe_payment_intent_id" in columns:
        op.drop_column("payments", "stripe_payment_intent_id")


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("payments")}
    if "stripe_session_id" not in columns:
        op.add_column("payments", sa.Column("stripe_session_id", sa.String(length=255), nullable=True))
        op.create_index("ix_payments_stripe_session_id", "payments", ["stripe_session_id"], unique=True)
    if "stripe_payment_intent_id" not in columns:
        op.add_column("payments", sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True))
        op.create_index("ix_payments_stripe_payment_intent_id", "payments", ["stripe_payment_intent_id"], unique=True)
