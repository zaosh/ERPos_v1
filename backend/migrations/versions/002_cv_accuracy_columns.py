"""Add CV accuracy tracking columns to items table.

Revision ID: 002
Revises: 001
Create Date: 2026-05-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("items", sa.Column("cv_color_correct", sa.Boolean(), nullable=True))
    op.add_column("items", sa.Column("cv_type_correct", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "cv_type_correct")
    op.drop_column("items", "cv_color_correct")
