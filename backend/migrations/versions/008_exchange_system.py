"""Add exchange system: exchanges table, bill_history, item/sale columns, new enums.

Revision ID: 008
Revises: 007
Create Date: 2026-05-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Add 'exchanged' to existing item_status enum ──────────────────────
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction on older Postgres.
    # We commit the current transaction, add the value, then start a new one.
    op.execute("COMMIT")
    op.execute("ALTER TYPE item_status ADD VALUE IF NOT EXISTS 'exchanged'")
    op.execute("BEGIN")

    # ── 2. New ENUM types ─────────────────────────────────────────────────────
    returned_item_condition_enum = postgresql.ENUM(
        "excellent", "good", "fair", "worn", "damaged",
        name="returned_item_condition_enum",
    )
    returned_item_condition_enum.create(conn, checkfirst=True)

    exchange_status_enum = postgresql.ENUM(
        "pending", "completed", "cancelled",
        name="exchange_status_enum",
    )
    exchange_status_enum.create(conn, checkfirst=True)

    bill_event_type_enum = postgresql.ENUM(
        "purchase",
        "exchange_initiated", "exchange_completed",
        "return_initiated", "return_completed",
        "item_added",
        name="bill_event_type_enum",
    )
    bill_event_type_enum.create(conn, checkfirst=True)

    # ── 3. New columns on items ───────────────────────────────────────────────
    op.add_column("items", sa.Column(
        "exchange_eligible", sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("items", sa.Column(
        "exchange_fee_paid", sa.Numeric(10, 2), nullable=True))
    op.add_column("items", sa.Column(
        "is_exchange_item", sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("items", sa.Column(
        "exchange_marker_detected", sa.Boolean, nullable=True))
    op.add_column("items", sa.Column(
        "original_item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=True))
    op.add_column("items", sa.Column(
        "exchanged_at", sa.TIMESTAMP(timezone=True), nullable=True))

    # Partial indexes — most rows are FALSE; partial keeps indexes tiny
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_items_is_exchange_item "
        "ON items(is_exchange_item) WHERE is_exchange_item = TRUE"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_items_exchange_eligible "
        "ON items(exchange_eligible) WHERE exchange_eligible = TRUE"
    ))

    # ── 4. New column on sales ────────────────────────────────────────────────
    op.add_column("sales", sa.Column(
        "exchange_fee_total",
        sa.Numeric(10, 2),
        nullable=False,
        server_default=sa.text("0"),
    ))

    # ── 5. exchanges table ────────────────────────────────────────────────────
    op.create_table(
        "exchanges",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("exchange_ref", sa.String(30), nullable=False),
        sa.Column("original_sale_id", sa.Integer, sa.ForeignKey("sales.id"), nullable=False),
        sa.Column("original_item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("new_item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=True),
        sa.Column("customer_id", sa.BigInteger, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("exchange_reason", sa.Text, nullable=False),
        sa.Column(
            "returned_item_condition",
            postgresql.ENUM(name="returned_item_condition_enum", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "returned_item_image_confirmed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("exchange_fee", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="exchange_status_enum", create_type=False),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("processed_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("exchange_ref", name="uq_exchanges_exchange_ref"),
        sa.UniqueConstraint("original_item_id", name="uq_exchanges_original_item"),
        sa.UniqueConstraint("new_item_id", name="uq_exchanges_new_item"),
        sa.CheckConstraint("returned_item_image_confirmed = TRUE", name="chk_exchanges_image_confirmed"),
    )
    op.create_index("idx_exchanges_sale", "exchanges", ["original_sale_id"])
    op.create_index("idx_exchanges_customer", "exchanges", ["customer_id"])
    op.create_index("idx_exchanges_status", "exchanges", ["status"])
    op.create_index("idx_exchanges_tenant_id", "exchanges", ["tenant_id"])

    # ── 6. bill_history table ─────────────────────────────────────────────────
    op.create_table(
        "bill_history",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("sale_id", sa.Integer, sa.ForeignKey("sales.id"), nullable=False),
        sa.Column(
            "event_type",
            postgresql.ENUM(name="bill_event_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=True),
        sa.Column("exchange_id", sa.BigInteger, sa.ForeignKey("exchanges.id"), nullable=True),
        sa.Column("return_id", sa.BigInteger, sa.ForeignKey("returns.id"), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("tenant_id", sa.Integer, nullable=False, server_default=sa.text("1")),
    )
    op.create_index("idx_bill_history_sale", "bill_history", ["sale_id"])
    op.create_index("idx_bill_history_created_at", "bill_history", ["created_at"])
    op.create_index("idx_bill_history_tenant_id", "bill_history", ["tenant_id"])

    # ── 7. Seed system_settings ───────────────────────────────────────────────
    conn.execute(sa.text("""
        INSERT INTO system_settings (key, value, description) VALUES
        ('exchange_window_days', '30', 'Days after purchase during which exchange is allowed'),
        ('exchange_fee_amount',  '0',  'Flat exchange fee charged at original sale time (per item, in INR)')
        ON CONFLICT (key) DO NOTHING
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # Seeds
    conn.execute(sa.text(
        "DELETE FROM system_settings WHERE key IN ('exchange_window_days', 'exchange_fee_amount')"
    ))

    # Tables
    op.drop_table("bill_history")
    op.drop_table("exchanges")

    # Sales column
    op.drop_column("sales", "exchange_fee_total")

    # Items columns + partial indexes
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_items_exchange_eligible"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_items_is_exchange_item"))
    op.drop_column("items", "exchanged_at")
    op.drop_column("items", "original_item_id")
    op.drop_column("items", "exchange_marker_detected")
    op.drop_column("items", "is_exchange_item")
    op.drop_column("items", "exchange_fee_paid")
    op.drop_column("items", "exchange_eligible")

    # Drop new enum types
    conn.execute(sa.text("DROP TYPE IF EXISTS bill_event_type_enum"))
    conn.execute(sa.text("DROP TYPE IF EXISTS exchange_status_enum"))
    conn.execute(sa.text("DROP TYPE IF EXISTS returned_item_condition_enum"))

    # NOTE: Cannot remove 'exchanged' from item_status enum in PostgreSQL without
    # recreating the type. The 'exchanged' value will remain in the enum after downgrade.
    # This is safe — no rows will have status='exchanged' after downgrade since we
    # dropped the exchanges table. Any such rows would need to be manually fixed.
