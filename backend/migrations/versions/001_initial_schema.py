"""Initial schema — all tables and enum types.

Revision ID: 001
Revises:
Create Date: 2026-04-29
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS btree_gin"))

    user_role = postgresql.ENUM("staff", "admin", "superadmin", name="user_role")
    user_role.create(conn)

    item_category = postgresql.ENUM(
        "tshirt", "pants", "jacket", "dress", "skirt", "shorts", "sweater", "hoodie", "other",
        name="item_category",
    )
    item_category.create(conn)

    item_type = postgresql.ENUM(
        "plain", "graphic", "patterned", "striped", "band", "anime", "sports",
        "vintage_graphic", "holiday", "branded", "statement", "unknown",
        name="item_type",
    )
    item_type.create(conn)

    item_condition = postgresql.ENUM("excellent", "good", "fair", "worn", name="item_condition")
    item_condition.create(conn)

    item_status = postgresql.ENUM("in_stock", "sold", "reserved", "archived", name="item_status")
    item_status.create(conn)

    payment_type = postgresql.ENUM("cash", "card", "other", name="payment_type")
    payment_type.create(conn)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", postgresql.ENUM("staff", "admin", "superadmin", name="user_role", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_users_username", "users", ["username"])

    op.create_table(
        "items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("barcode", sa.String(20), unique=True, nullable=False),
        sa.Column("category", postgresql.ENUM("tshirt", "pants", "jacket", "dress", "skirt", "shorts", "sweater", "hoodie", "other", name="item_category", create_type=False), nullable=False),
        sa.Column("color", sa.String(30)),
        sa.Column("secondary_color", sa.String(30)),
        sa.Column("type", postgresql.ENUM("plain", "graphic", "patterned", "striped", "band", "anime", "sports", "vintage_graphic", "holiday", "branded", "statement", "unknown", name="item_type", create_type=False), nullable=False),
        sa.Column("label", sa.String(100)),
        sa.Column("size", sa.String(10)),
        sa.Column("condition", postgresql.ENUM("excellent", "good", "fair", "worn", name="item_condition", create_type=False), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("cv_confidence", sa.Float),
        sa.Column("cv_raw_output", postgresql.JSONB),
        sa.Column("image_path", sa.String(500)),
        sa.Column("image_thumb_path", sa.String(500)),
        sa.Column("status", postgresql.ENUM("in_stock", "sold", "reserved", "archived", name="item_status", create_type=False), nullable=False, server_default="in_stock"),
        sa.Column("notes", sa.Text),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sold_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index("idx_items_status", "items", ["status"])
    op.create_index("idx_items_category_color", "items", ["category", "color"])
    op.create_index("idx_items_label", "items", ["label"])
    op.create_index("idx_items_created_at", "items", ["created_at"])
    op.create_index("idx_items_sold_at", "items", ["sold_at"])

    op.create_table(
        "sales",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sale_ref", sa.String(20), unique=True, nullable=False),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("payment_type", postgresql.ENUM("cash", "card", "other", name="payment_type", create_type=False), nullable=False),
        sa.Column("cashier_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("voided_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("voided_by", sa.Integer, sa.ForeignKey("users.id")),
    )

    op.create_table(
        "sale_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sale_id", sa.Integer, sa.ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("table_name", sa.String(50), nullable=False),
        sa.Column("record_id", sa.Integer, nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("old_values", postgresql.JSONB),
        sa.Column("new_values", postgresql.JSONB),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("ip_address", postgresql.INET),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("idx_audit_table_record", "audit_log", ["table_name", "record_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("sale_items")
    op.drop_table("sales")
    op.drop_table("items")
    op.drop_table("users")

    conn = op.get_bind()
    for enum_name in ("payment_type", "item_status", "item_condition", "item_type", "item_category", "user_role"):
        conn.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))
