"""create contracts table

Revision ID: 001_contracts
Revises:
Create Date: 2026-09-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "001_contracts"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTRACT_STATUSES = (
    "pending",
    "funded",
    "in_progress",
    "submitted",
    "approved",
    "completed",
    "cancelled",
    "disputed",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "contracts" in inspector.get_table_names():
        return

    status_list = ", ".join(f"'{value}'" for value in CONTRACT_STATUSES)
    op.execute(
        f"""
        DO $$ BEGIN
            CREATE TYPE contract_status AS ENUM ({status_list});
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposal_id", sa.Integer(), sa.ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("freelancer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agreed_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("platform_fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("freelancer_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("status", sa.Enum(*CONTRACT_STATUSES, name="contract_status", create_type=False), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", name="uq_contract_project"),
        sa.UniqueConstraint("proposal_id", name="uq_contract_proposal"),
    )
    op.create_index("ix_contracts_id", "contracts", ["id"])
    op.create_index("ix_contracts_project_id", "contracts", ["project_id"])
    op.create_index("ix_contracts_proposal_id", "contracts", ["proposal_id"])
    op.create_index("ix_contracts_client_id", "contracts", ["client_id"])
    op.create_index("ix_contracts_freelancer_id", "contracts", ["freelancer_id"])
    op.create_index("ix_contracts_status", "contracts", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "contracts" in inspector.get_table_names():
        op.drop_table("contracts")
    op.execute("DROP TYPE IF EXISTS contract_status")
