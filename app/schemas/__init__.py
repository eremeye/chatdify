"""Pydantic v2 DTO schemas for API requests/responses.

This package contains all Data Transfer Object (DTO) schemas built with Pydantic v2.
For comprehensive documentation, usage examples, and best practices, see:
    app/schemas/README.md

Quick Import Guide:
    from app.schemas import (
        # Conversation schemas
        ConversationCreate, ConversationResponse, ConversationUpdateRequest,
        ConversationPriority, ConversationStatus,
        # Chatwoot schemas  
        ChatwootWebhook, ChatwootSender, ChatwootConversation,
        # Dify schemas
        DifyResponse
    )

Key Features:
    - Type-safe validation with Pydantic v2
    - Seamless ORM integration with from_attributes=True
    - Computed fields for derived properties
    - Consistent model_validate() and model_dump() patterns
"""

# Conversation schemas
# Chatwoot webhook schemas
from app.schemas.chatwoot import (
    ChatwootConversation,
    ChatwootMessage,
    ChatwootMeta,
    ChatwootSender,
    ChatwootWebhook,
)
from app.schemas.conversation import (
    ConversationCreate,
    ConversationCreateRequest,
    ConversationPriority,
    ConversationResponse,
    ConversationStatus,
    ConversationUpdateRequest,
)

# Dify integration schemas
from app.schemas.dify import DifyResponse

__all__ = [
    # Conversation schemas
    "ConversationCreate",
    "ConversationCreateRequest",
    "ConversationResponse",
    "ConversationUpdateRequest",
    "ConversationPriority",
    "ConversationStatus",
    # Chatwoot schemas
    "ChatwootSender",
    "ChatwootMeta",
    "ChatwootConversation",
    "ChatwootMessage",
    "ChatwootWebhook",
    # Dify schemas
    "DifyResponse",
]
