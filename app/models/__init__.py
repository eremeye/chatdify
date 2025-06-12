"""Database and data models package."""

# Database models (SQLAlchemy 2)
from app.db.models import Dialogue

# Non-database models (Pydantic)
from app.models.non_database import (
    ChatwootConversation,
    ChatwootMessage,
    ChatwootMeta,
    ChatwootSender,
    ChatwootWebhook,
    ConversationPriority,
    ConversationStatus,
    DialogueCreate,
    DifyResponse,
)

__all__ = [
    # Database models
    "Dialogue",
    # Non-database models
    "DialogueCreate",
    "ChatwootWebhook",
    "ChatwootSender",
    "ChatwootMeta",
    "ChatwootConversation",
    "ChatwootMessage",
    "DifyResponse",
    "ConversationPriority",
    "ConversationStatus",
]
