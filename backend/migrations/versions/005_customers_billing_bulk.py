"""Add customers, billing fields, returns, bulk intake, system_settings.

Revision ID: 005
Revises: 004
Create Date: 2026-05-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SYSTEM_SETTINGS_SEED = [
    {"key": "tax_rate", "value": "0.0000", "description": "Sales tax rate as decimal (e.g. 0.0875 = 8.75%)"},
    {"key": "store_name", "value": "qstar", "description": "Store display name on receipts"},
    {"key": "receipt_footer", "value": "Thank you for shopping with us", "description": "Footer line on printed receipts"},
    {"key": "return_window_days", "value": "14", "description": "Days after sale within which returns are accepted"},
]


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. New enums ──────────────────────────────────────────────────────────
    refund_method_enum = postgresql.ENUM(
        "cash", "card", "store_credit",
        name="refund_method_enum",
    )
    refund_method_enum.create(conn)

    return_status_enum = postgresql.ENUM(
        "pending", "approved", "completed", "rejected",
        name="return_status_enum",
    )
    return_status_enum.create(conn)

    # ── 2. Bulk columns on items ──────────────────────────────────────────────
    op.add_column("items", sa.Column("bulk_group_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("items", sa.Column("bulk_sequence", sa.Integer, nullable=True))
    op.create_index(
        "idx_items_bulk_group_id", "items", ["bulk_group_id"],
        postgresql_where=sa.text("bulk_group_id IS NOT NULL"),
    )

    # ── 3. customers table ────────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("customer_uid", sa.String(20), nullable=False),
        sa.Column("first_name", sa.String(80), nullable=True),
        sa.Column("last_name", sa.String(80), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("gdpr_erased_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Integer, nullable=True, server_default="1"),
    )
    op.create_index("idx_customers_customer_uid", "customers", ["customer_uid"], unique=True)
    # Partial unique index for phone: allow NULL (GDPR-erased) but not duplicate active phones
    conn.execute(sa.text(
        "CREATE UNIQUE INDEX idx_customers_phone_unique ON customers (phone) WHERE phone IS NOT NULL"
    ))
    op.create_index("idx_customers_last_name", "customers", ["last_name"])
    op.create_index("idx_customers_created_at", "customers", ["created_at"])
    op.create_index("idx_customers_tenant_id", "customers", ["tenant_id"])

    # ── 4. system_settings table + seed ──────────────────────────────────────
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("tenant_id", sa.Integer, nullable=True, server_default="1"),
    )
    op.create_index("idx_system_settings_tenant_id", "system_settings", ["tenant_id"])
    settings_table = sa.table(
        "system_settings",
        sa.column("key", sa.String),
        sa.column("value", sa.Text),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(settings_table, _SYSTEM_SETTINGS_SEED)

    # ── 5. Add billing columns to sales (nullable first for backfill) ─────────
    # Rename discount → discount_amount
    op.alter_column("sales", "discount", new_column_name="discount_amount")
    op.add_column("sales", sa.Column("customer_id", sa.BigInteger, sa.ForeignKey("customers.id"), nullable=True))
    op.add_column("sales", sa.Column("receipt_number", sa.String(30), nullable=True))
    op.add_column("sales", sa.Column("subtotal", sa.Numeric(10, 2), nullable=True))
    op.add_column("sales", sa.Column("tax_rate", sa.Numeric(5, 4), nullable=False, server_default="0"))
    op.add_column("sales", sa.Column("tax_amount", sa.Numeric(10, 2), nullable=False, server_default="0"))

    # ── 6. Backfill existing sales ────────────────────────────────────────────
    conn.execute(sa.text("UPDATE sales SET subtotal = total_amount WHERE subtotal IS NULL"))
    conn.execute(sa.text("""
        WITH numbered AS (
            SELECT id,
                   'RCP-' || to_char(created_at AT TIME ZONE 'UTC', 'YYYYMMDD') || '-' ||
                   lpad(row_number() OVER (
                       PARTITION BY date(created_at AT TIME ZONE 'UTC')
                       ORDER BY id
                   )::text, 4, '0') AS rcp
            FROM sales
            WHERE receipt_number IS NULL
        )
        UPDATE sales s SET receipt_number = n.rcp FROM numbered n WHERE s.id = n.id
    """))

    # ── 7. Tighten sales constraints ──────────────────────────────────────────
    op.alter_column("sales", "subtotal", nullable=False)
    op.alter_column("sales", "receipt_number", nullable=False)
    op.create_index("ux_sales_receipt_number", "sales", ["receipt_number"], unique=True)
    op.create_index(
        "idx_sales_customer_id", "sales", ["customer_id"],
        postgresql_where=sa.text("customer_id IS NOT NULL"),
    )

    # ── 8. returns table ──────────────────────────────────────────────────────
    op.create_table(
        "returns",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("return_ref", sa.String(30), nullable=False),
        sa.Column("original_sale_id", sa.Integer, sa.ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_id", sa.BigInteger, sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("return_reason", sa.Text, nullable=False),
        sa.Column("processed_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("refund_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("refund_method", postgresql.ENUM(name="refund_method_enum", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="return_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Integer, nullable=True, server_default="1"),
        sa.UniqueConstraint("return_ref", name="uq_returns_return_ref"),
    )
    op.create_index("idx_returns_original_sale_id", "returns", ["original_sale_id"])
    op.create_index("idx_returns_customer_id", "returns", ["customer_id"])
    op.create_index("idx_returns_tenant_id", "returns", ["tenant_id"])

    # ── 9. return_items table ─────────────────────────────────────────────────
    op.create_table(
        "return_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("return_id", sa.BigInteger, sa.ForeignKey("returns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("original_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("refund_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("tenant_id", sa.Integer, nullable=True, server_default="1"),
        sa.UniqueConstraint("item_id", name="uq_return_items_item_id"),
    )
    op.create_index("idx_return_items_return_id", "return_items", ["return_id"])
    op.create_index("idx_return_items_tenant_id", "return_items", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("return_items")
    op.drop_table("returns")

    op.drop_index("idx_sales_customer_id", table_name="sales")
    op.drop_index("ux_sales_receipt_number", table_name="sales")
    op.drop_column("sales", "tax_amount")
    op.drop_column("sales", "tax_rate")
    op.drop_column("sales", "subtotal")
    op.drop_column("sales", "receipt_number")
    op.drop_column("sales", "customer_id")
    op.alter_column("sales", "discount_amount", new_column_name="discount")

    op.drop_table("system_settings")
    op.drop_table("customers")

    op.drop_index("idx_items_bulk_group_id", table_name="items")
    op.drop_column("items", "bulk_sequence")
    op.drop_column("items", "bulk_group_id")

    conn = op.get_bind()
    conn.execute(sa.text("DROP TYPE IF EXISTS return_status_enum"))
    conn.execute(sa.text("DROP TYPE IF EXISTS refund_method_enum"))
