"""Add DEFAULT NOW() to audit_log.created_at (was missing from initial schema).

Revision ID: 003
Revises: 002
Create Date: 2026-05-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "audit_log",
        "created_at",
        server_default=sa.func.now(),
        existing_type=sa.TIMESTAMP(timezone=True),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "audit_log",
        "created_at",
        server_default=None,
        existing_type=sa.TIMESTAMP(timezone=True),
        existing_nullable=False,
    )
