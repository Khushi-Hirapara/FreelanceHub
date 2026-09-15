"""milestones and stripe payment columns

Revision ID: 003_milestones
Revises: 002_payments
Create Date: 2026-09-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "003_milestones"
down_revision: Union[str, None] = "002_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MILESTONE_STATUSES = (
    "pending",
    "funded",
    "in_progress",
    "submitted",
    "approved",
    "released",
    "cancelled",
    "disputed",
)
ACTIVE_PAYMENT = (
    "status IN ('pending'::payment_status, 'processing'::payment_status, 'paid'::payment_status)"
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    listed = ", ".join(f"'{value}'" for value in MILESTONE_STATUSES)
    op.execute(
        f"""
        DO $$ BEGIN
            CREATE TYPE milestone_status AS ENUM ({listed});
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    if "milestones" not in inspector.get_table_names():
        op.create_table(
            "milestones",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "status",
                postgresql.ENUM(*MILESTONE_STATUSES, name="milestone_status", create_type=False),
                nullable=False,
            ),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_milestones_id", "milestones", ["id"])
        op.create_index("ix_milestones_contract_id", "milestones", ["contract_id"])
        op.create_index("ix_milestones_status", "milestones", ["status"])

    payment_columns = {column["name"] for column in inspect(bind).get_columns("payments")}
    if "milestone_id" not in payment_columns:
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
    if "stripe_session_id" not in payment_columns:
        op.add_column("payments", sa.Column("stripe_session_id", sa.String(length=255), nullable=True))
        op.create_index("ix_payments_stripe_session_id", "payments", ["stripe_session_id"], unique=True)
    if "stripe_payment_intent_id" not in payment_columns:
        op.add_column("payments", sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True))
        op.create_index("ix_payments_stripe_payment_intent_id", "payments", ["stripe_payment_intent_id"], unique=True)
    if "released_at" not in payment_columns:
        op.add_column("payments", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))

    op.alter_column("payments", "transaction_id", existing_type=sa.String(length=40), type_=sa.String(length=255))

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'stripe'")

    op.execute("DROP INDEX IF EXISTS uq_payment_active_contract")
    op.execute("DROP INDEX IF EXISTS uq_payment_active_milestone")
    op.execute(
        "CREATE UNIQUE INDEX uq_payment_active_contract ON payments (contract_id) "
        f"WHERE milestone_id IS NULL AND {ACTIVE_PAYMENT}"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_payment_active_milestone ON payments (milestone_id) "
        f"WHERE milestone_id IS NOT NULL AND {ACTIVE_PAYMENT}"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_payment_active_milestone")
    op.execute("DROP INDEX IF EXISTS uq_payment_active_contract")
    op.execute(
        "CREATE UNIQUE INDEX uq_payment_active_contract ON payments (contract_id) "
        f"WHERE {ACTIVE_PAYMENT}"
    )
    op.drop_index("ix_payments_stripe_payment_intent_id", table_name="payments")
    op.drop_index("ix_payments_stripe_session_id", table_name="payments")
    op.drop_constraint("fk_payments_milestone_id", "payments", type_="foreignkey")
    op.drop_index("ix_payments_milestone_id", table_name="payments")
    op.drop_column("payments", "released_at")
    op.drop_column("payments", "stripe_payment_intent_id")
    op.drop_column("payments", "stripe_session_id")
    op.drop_column("payments", "milestone_id")
    op.drop_index("ix_milestones_status", table_name="milestones")
    op.drop_index("ix_milestones_contract_id", table_name="milestones")
    op.drop_index("ix_milestones_id", table_name="milestones")
    op.drop_table("milestones")
    op.execute("DROP TYPE IF EXISTS milestone_status")
