"""
app/models/base.py
Shared SQLAlchemy model mixins.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import ulid
from sqlalchemy import DateTime, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base  # noqa: F401 re-exported for convenience


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_ulid() -> str:
    return str(ulid.new())


class TimestampMixin:
    """Adds created_at / updated_at columns to any model."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class SoftDeleteMixin:
    """Adds is_deleted / deleted_at columns; rows are never hard-deleted."""
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.deleted_at = _now()


class ULIDPrimaryKeyMixin:
    """ULID string primary key — sortable, URL-safe, collision-resistant."""
    id: Mapped[str] = mapped_column(
        String(26), primary_key=True, default=_new_ulid, index=True
    )
