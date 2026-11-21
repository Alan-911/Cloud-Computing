from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Item(Base):
    """Mirrors migrations/versions/0001_create_items.py. Change the schema with a
    new migration; tests fail if the two drift apart."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_items_name_not_blank"),
        # Names are unique regardless of case, enforced by the database.
        Index("uq_items_name_lower", func.lower(name), unique=True),
    )
