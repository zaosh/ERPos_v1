"""Add job_queue table and Phase B columns to items.

Revision ID: 004
Revises: 003
Create Date: 2026-05-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Phase B columns on items
    op.add_column("items", sa.Column("cv_phase_b_complete", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("items", sa.Column("fashion_attributes", postgresql.JSONB(), nullable=True))

    # Enums for job_queue
    job_type_enum = postgresql.ENUM(
        "cv_phase_a", "cv_phase_b", "fashion_attributes", "print_label", "print_retry",
        name="job_type_enum",
    )
    job_type_enum.create(conn)

    job_status_enum = postgresql.ENUM(
        "pending", "processing", "complete", "failed", "cancelled",
        name="job_status_enum",
    )
    job_status_enum.create(conn)

    # job_queue table
    op.create_table(
        "job_queue",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("job_type", postgresql.ENUM(name="job_type_enum", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="job_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="5"),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )

    op.create_index("ix_job_queue_poll", "job_queue", ["status", "priority", "created_at"])
    op.create_index("ix_job_queue_item_id", "job_queue", ["item_id"])
    op.create_index("ix_job_queue_type_status", "job_queue", ["job_type", "status"])


def downgrade() -> None:
    op.drop_index("ix_job_queue_type_status", table_name="job_queue")
    op.drop_index("ix_job_queue_item_id", table_name="job_queue")
    op.drop_index("ix_job_queue_poll", table_name="job_queue")
    op.drop_table("job_queue")

    conn = op.get_bind()
    conn.execute(sa.text("DROP TYPE IF EXISTS job_status_enum"))
    conn.execute(sa.text("DROP TYPE IF EXISTS job_type_enum"))

    op.drop_column("items", "fashion_attributes")
    op.drop_column("items", "cv_phase_b_complete")
