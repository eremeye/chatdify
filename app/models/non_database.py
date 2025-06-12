from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ConversationPriority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = None


class ConversationStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    PENDING = "pending"


# Data models for validation and creation (using Pydantic instead of SQLModel)
class DialogueCreate(BaseModel):
    chatwoot_conversation_id: str
    status: str = "pending"
    assignee_id: Optional[int] = None
    dify_conversation_id: Optional[str] = None


# Chatwoot webhook models
class ChatwootSender(BaseModel):
    id: Optional[int] = None
    type: Optional[str] = None  # "user", "agent_bot", etc.


class ChatwootMeta(BaseModel):
    assignee: Optional[dict] = None

    @property
    def assignee_id(self) -> Optional[int]:
        return self.assignee.get("id") if self.assignee else None


class ChatwootConversation(BaseModel):
    id: int
    status: str = "pending"
    inbox_id: Optional[int] = None
    meta: ChatwootMeta = Field(default_factory=ChatwootMeta)

    @property
    def assignee_id(self) -> Optional[int]:
        return self.meta.assignee_id


class ChatwootMessage(BaseModel):
    id: int
    content: str
    message_type: Literal["incoming", "outgoing"]
    conversation: ChatwootConversation
    sender: ChatwootSender


class ChatwootWebhook(BaseModel):
    event: str
    message_type: Literal["incoming", "outgoing"]  # TODO: ideally remove this
    sender: Optional[ChatwootSender] = None  # From payload["sender"]
    message: Optional[ChatwootMessage] = None
    conversation: Optional[ChatwootConversation] = None
    content: Optional[str] = None  # From payload["content"]
    echo_id: Optional[str] = None  # To identify AI-generated messages

    @property
    def sender_id(self) -> Optional[int]:
        """Get sender ID from the top-level sender field"""
        return self.sender.id if self.sender else None

    @property
    def conversation_id(self) -> Optional[int]:
        """Get conversation ID from either message or conversation"""
        if self.message and self.message.conversation:
            return self.message.conversation.id
        elif self.conversation:
            return self.conversation.id
        return None

    @property
    def assignee_id(self) -> Optional[int]:
        """Get assignee ID from conversation meta"""
        if self.message and self.message.conversation:
            return self.message.conversation.assignee_id
        elif self.conversation:
            return self.conversation.assignee_id
        return None

    @property
    def derived_message_type(self) -> Optional[str]:
        """Get message type from the nested message object"""
        return self.message.message_type if self.message else None

    @property
    def status(self) -> Optional[str]:
        """Get status from conversation"""
        if self.conversation:
            return self.conversation.status
        return None

    @property
    def sender_type(self) -> Optional[str]:
        """Get sender type"""
        return self.sender.type if self.sender else None

    def to_dialogue_create(self) -> DialogueCreate:
        return DialogueCreate(
            chatwoot_conversation_id=str(self.conversation_id),
            status=self.status or "pending",
            assignee_id=self.assignee_id,
        )


class DifyResponse(BaseModel):
    event: Optional[str] = None
    task_id: Optional[str] = None
    id: Optional[str] = None
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    mode: Optional[str] = None
    answer: str  # This is the only required field
    response_metadata: Optional[dict] = None
    created_at: Optional[int] = None

    @classmethod
    def error_response(cls) -> "DifyResponse":
        """Create an error response object"""
        return cls(
            answer=(
                "I apologize, but I'm temporarily unavailable. "
                "Please try again later or wait for a human operator to respond."
            )
        )
