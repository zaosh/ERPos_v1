"""Add default_phone_region to system_settings.

Revision ID: 007
Revises: 006
Create Date: 2026-05-08
"""
from typing import Union
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO system_settings (key, value, description)
        VALUES (
            'default_phone_region',
            'IN',
            'BCP-47 region code used for phone number parsing (e.g. IN, US, GB)'
        )
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE key = 'default_phone_region'"
    )
