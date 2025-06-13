"""SQLAlchemy 2 database models with dataclass mapping."""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Conversation(Base):
    """Conversation table model using SQLAlchemy 2 with dataclass mapping."""
    
    __tablename__ = "conversation"
    
    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True)
    chatwoot_conversation_id: Mapped[str] = mapped_column(index=True)
    dify_conversation_id: Mapped[Optional[str]] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(default="pending")
    assignee_id: Mapped[Optional[int]] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        insert_default=lambda: datetime.now(UTC),
        nullable=False,
        init=False,
        default_factory=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        insert_default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        init=False,
        default_factory=lambda: datetime.now(UTC)
    ) 