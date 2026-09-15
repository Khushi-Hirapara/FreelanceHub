"""create payments table

Revision ID: 002_payments
Revises: 001_contracts
Create Date: 2026-09-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "002_payments"
down_revision: Union[str, None] = "001_contracts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PAYMENT_STATUSES = ("pending", "processing", "paid", "failed", "refunded", "cancelled")


def _enum(name: str, values: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"""
        DO $$ BEGIN
            CREATE TYPE {name} AS ENUM ({listed});
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    _enum("payment_status", PAYMENT_STATUSES)
    _enum("payment_method", ("mock_card",))

    if "payments" not in tables:
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("freelancer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("platform_fee", sa.Numeric(12, 2), nullable=False),
            sa.Column("freelancer_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column(
                "payment_method",
                postgresql.ENUM("mock_card", name="payment_method", create_type=False),
                nullable=False,
            ),
            sa.Column("transaction_id", sa.String(length=40), nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM(*PAYMENT_STATUSES, name="payment_status", create_type=False),
                nullable=False,
            ),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_payments_id", "payments", ["id"])
        op.create_index("ix_payments_contract_id", "payments", ["contract_id"])
        op.create_index("ix_payments_client_id", "payments", ["client_id"])
        op.create_index("ix_payments_freelancer_id", "payments", ["freelancer_id"])
        op.create_index("ix_payments_status", "payments", ["status"])
        op.create_index("ix_payments_transaction_id", "payments", ["transaction_id"], unique=True)

    indexes = {item["name"] for item in inspect(bind).get_indexes("payments")}
    if "uq_payment_active_contract" not in indexes:
        op.create_index(
            "uq_payment_active_contract",
            "payments",
            ["contract_id"],
            unique=True,
            postgresql_where=sa.text(
                "status IN ('pending'::payment_status, 'processing'::payment_status, 'paid'::payment_status)"
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "payments" in inspector.get_table_names():
        op.drop_table("payments")
    op.execute("DROP TYPE IF EXISTS payment_status")
    op.execute("DROP TYPE IF EXISTS payment_method")
