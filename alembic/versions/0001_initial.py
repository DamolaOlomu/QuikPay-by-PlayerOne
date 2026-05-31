"""initial_schema

Revision ID: 0001_initial
Revises:
Create Date: 2025-05-31 00:00:00.000000

"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("fullname", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("pin_hash", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="customer"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_verification"),
        sa.Column("api_key_hash", sa.String(255), nullable=True),
        sa.Column("balance", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="NGN"),
        sa.Column("last_idempotency_key", sa.String(64), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_phone_number", "users", ["phone_number"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_is_deleted", "users", ["is_deleted"])
    op.create_index("ix_users_api_key_hash", "users", ["api_key_hash"])

    # ── kyc ───────────────────────────────────────────────────────────────────
    op.create_table(
        "kyc",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier", sa.String(10), nullable=False, server_default="tier_0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("bvn", sa.String(11), nullable=True),
        sa.Column("nin", sa.String(11), nullable=True),
        sa.Column("id_type", sa.String(50), nullable=True),
        sa.Column("id_number", sa.String(50), nullable=True),
        sa.Column("id_expiry", sa.String(20), nullable=True),
        sa.Column("id_front_ref", sa.String(255), nullable=True),
        sa.Column("id_back_ref", sa.String(255), nullable=True),
        sa.Column("selfie_ref", sa.String(255), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("reviewer_id", sa.String(26), nullable=True),
        sa.Column("daily_limit", sa.Numeric(18, 2), nullable=False, server_default="50000"),
        sa.Column("monthly_limit", sa.Numeric(18, 2), nullable=False, server_default="200000"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kyc_user_id", "kyc", ["user_id"], unique=True)

    # ── transactions ──────────────────────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("reference", sa.String(64), nullable=False, unique=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True, unique=True),
        sa.Column("external_reference", sa.String(128), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("fee", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("balance_before", sa.Numeric(18, 4), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="NGN"),
        sa.Column("transaction_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="initiated"),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("counterparty_id", sa.String(26), nullable=True),
        sa.Column("counterparty_name", sa.String(255), nullable=True),
        sa.Column("counterparty_account", sa.String(50), nullable=True),
        sa.Column("reversed_by_id", sa.String(26), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])
    op.create_index("ix_transactions_reference", "transactions", ["reference"])
    op.create_index("ix_transactions_status", "transactions", ["status"])
    op.create_index("ix_transactions_type", "transactions", ["transaction_type"])

    # ── transaction_events ────────────────────────────────────────────────────
    op.create_table(
        "transaction_events",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("transaction_id", sa.String(26), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transaction_events_transaction_id", "transaction_events", ["transaction_id"])

    # ── agents ────────────────────────────────────────────────────────────────
    op.create_table(
        "agents",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("kyc_id", sa.String(26), sa.ForeignKey("kyc.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="inactive"),
        sa.Column("address", sa.Text, nullable=False),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("lga", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("float_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("daily_transaction_limit", sa.Numeric(18, 2), nullable=False, server_default="500000"),
        sa.Column("commission_rate", sa.Float, nullable=False, server_default="0.005"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── atms ──────────────────────────────────────────────────────────────────
    op.create_table(
        "atms",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("terminal_id", sa.String(50), nullable=False, unique=True),
        sa.Column("bank_name", sa.String(100), nullable=True),
        sa.Column("bank_code", sa.String(10), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="offline"),
        sa.Column("address", sa.Text, nullable=False),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("cash_level", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("max_cash_capacity", sa.Numeric(18, 2), nullable=False, server_default="5000000"),
        sa.Column("last_serviced_by", sa.String(26), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── payment_links ─────────────────────────────────────────────────────────
    op.create_table(
        "payment_links",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("creator_id", sa.String(26), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="NGN"),
        sa.Column("collect_phone", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("collect_name", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("one_time_use", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("times_paid", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_collected", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_links_creator_id", "payment_links", ["creator_id"])


def downgrade() -> None:
    op.drop_table("payment_links")
    op.drop_table("atms")
    op.drop_table("agents")
    op.drop_table("transaction_events")
    op.drop_table("transactions")
    op.drop_table("kyc")
    op.drop_table("users")
