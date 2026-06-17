"""add_wallet_id

Revision ID: 0002_add_wallet_id
Revises: 0001_initial
Create Date: 2026-06-03 00:00:00.000000

"""
from __future__ import annotations

import secrets

from alembic import op
import sqlalchemy as sa

revision: str = "0002_add_wallet_id"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _new_wallet_id() -> str:
    return f"WLT{secrets.token_hex(8).upper()}"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}

    if "wallet_id" not in columns:
        op.add_column("users", sa.Column("wallet_id", sa.String(32), nullable=True))

    users = bind.execute(sa.text("SELECT id FROM users WHERE wallet_id IS NULL OR wallet_id = ''")).fetchall()
    for user in users:
        bind.execute(
            sa.text("UPDATE users SET wallet_id = :wallet_id WHERE id = :user_id"),
            {"wallet_id": _new_wallet_id(), "user_id": user.id},
        )

    if bind.dialect.name != "sqlite":
        op.alter_column("users", "wallet_id", existing_type=sa.String(32), nullable=False)

    indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_wallet_id" not in indexes:
        op.create_index("ix_users_wallet_id", "users", ["wallet_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_wallet_id" in indexes:
        op.drop_index("ix_users_wallet_id", table_name="users")

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "wallet_id" in columns:
        op.drop_column("users", "wallet_id")
