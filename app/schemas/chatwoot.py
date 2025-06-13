"""Chatwoot webhook-related Pydantic v2 DTO schemas."""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.schemas.conversation import ConversationCreate


class ChatwootSender(BaseModel):
    """Schema for Chatwoot message sender information."""
    model_config = ConfigDict(from_attributes=True)
    
    id: Optional[int] = Field(default=None, description="Sender ID")
    type: Optional[str] = Field(default=None, description="Sender type (user, agent_bot, etc.)")


class ChatwootMeta(BaseModel):
    """Schema for Chatwoot conversation metadata."""
    model_config = ConfigDict(from_attributes=True)
    
    assignee: Optional[dict] = Field(default=None, description="Assignee information")

    @computed_field
    @property
    def assignee_id(self) -> Optional[int]:
        """Extract assignee ID from assignee dictionary."""
        return self.assignee.get("id") if self.assignee else None


class ChatwootConversation(BaseModel):
    """Schema for Chatwoot conversation data."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Chatwoot conversation ID")
    status: str = Field(default="pending", description="Conversation status")
    inbox_id: Optional[int] = Field(default=None, description="Inbox ID where conversation belongs")
    meta: ChatwootMeta = Field(default_factory=ChatwootMeta, description="Conversation metadata")

    @computed_field
    @property
    def assignee_id(self) -> Optional[int]:
        """Get assignee ID from conversation metadata."""
        return self.meta.assignee_id


class ChatwootMessage(BaseModel):
    """Schema for Chatwoot message data."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Message ID")
    content: str = Field(..., description="Message content")
    message_type: Literal["incoming", "outgoing"] = Field(..., description="Direction of the message")
    conversation: ChatwootConversation = Field(..., description="Associated conversation")
    sender: ChatwootSender = Field(..., description="Message sender information")


class ChatwootWebhook(BaseModel):
    """Schema for Chatwoot webhook payloads with comprehensive validation."""
    model_config = ConfigDict(from_attributes=True)
    
    event: str = Field(..., description="Webhook event type")
    message_type: Literal["incoming", "outgoing"] = Field(..., description="Message direction type")
    sender: Optional[ChatwootSender] = Field(default=None, description="Sender from payload root")
    message: Optional[ChatwootMessage] = Field(default=None, description="Message data")
    conversation: Optional[ChatwootConversation] = Field(default=None, description="Conversation data")
    content: Optional[str] = Field(default=None, description="Content from payload root")
    echo_id: Optional[str] = Field(default=None, description="Echo ID for AI-generated message identification")

    @computed_field
    @property
    def sender_id(self) -> Optional[int]:
        """Get sender ID from the top-level sender field."""
        return self.sender.id if self.sender else None

    @computed_field
    @property
    def conversation_id(self) -> Optional[int]:
        """Get conversation ID from either message or conversation."""
        if self.message and self.message.conversation:
            return self.message.conversation.id
        elif self.conversation:
            return self.conversation.id
        return None

    @computed_field
    @property
    def assignee_id(self) -> Optional[int]:
        """Get assignee ID from conversation meta."""
        if self.message and self.message.conversation:
            return self.message.conversation.assignee_id
        elif self.conversation:
            return self.conversation.assignee_id
        return None

    @computed_field
    @property
    def derived_message_type(self) -> Optional[str]:
        """Get message type from the nested message object."""
        return self.message.message_type if self.message else None

    @computed_field
    @property
    def status(self) -> Optional[str]:
        """Get status from conversation."""
        if self.conversation:
            return self.conversation.status
        return None

    @computed_field
    @property
    def sender_type(self) -> Optional[str]:
        """Get sender type."""
        return self.sender.type if self.sender else None

    def to_conversation_create(self) -> ConversationCreate:
        """Convert webhook data to ConversationCreate schema."""
        return ConversationCreate(
            chatwoot_conversation_id=str(self.conversation_id),
            status=self.status or "pending",
            assignee_id=self.assignee_id,
        )
