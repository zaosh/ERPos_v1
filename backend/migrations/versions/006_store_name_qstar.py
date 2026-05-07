"""Update store_name setting to qstar.

Revision ID: 006
Revises: 005
Create Date: 2026-05-08
"""
from typing import Union
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE system_settings SET value = 'qstar' WHERE key = 'store_name'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE system_settings SET value = 'ThriftOS Store' WHERE key = 'store_name'"
    )
