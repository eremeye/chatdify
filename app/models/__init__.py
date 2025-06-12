"""Database and data models package."""

# Database models (SQLAlchemy 2)
from app.db.models import Conversation

# Non-database models (Pydantic)
from app.models.non_database import (
    ChatwootConversation,
    ChatwootMessage,
    ChatwootMeta,
    ChatwootSender,
    ChatwootWebhook,
    ConversationPriority,
    ConversationStatus,
    ConversationCreate,
    DifyResponse,
)

__all__ = [
    # Database models
    "Conversation",
    # Non-database models
    "ConversationCreate",
    "ChatwootWebhook",
    "ChatwootSender",
    "ChatwootMeta",
    "ChatwootConversation",
    "ChatwootMessage",
    "DifyResponse",
    "ConversationPriority",
    "ConversationStatus",
]
