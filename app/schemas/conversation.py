"""Conversation-related Pydantic v2 DTO schemas."""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ConversationPriority(str, Enum):
    """Enumeration for conversation priority levels."""
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = None


class ConversationStatus(str, Enum):
    """Enumeration for conversation status values."""
    OPEN = "open"
    RESOLVED = "resolved"
    PENDING = "pending"


class ConversationBase(BaseModel):
    """Base conversation schema with common fields."""
    model_config = ConfigDict(from_attributes=True)
    
    chatwoot_conversation_id: str = Field(..., description="ID of the conversation in Chatwoot")
    status: str = Field(default="pending", description="Current status of the conversation")
    assignee_id: Optional[int] = Field(default=None, description="ID of the assigned agent")
    dify_conversation_id: Optional[str] = Field(default=None, description="ID of the conversation in Dify")


class ConversationCreate(ConversationBase):
    """Schema for creating conversations - used internally for database operations."""
    pass


class ConversationCreateRequest(BaseModel):
    """Schema for API requests to create conversations."""
    model_config = ConfigDict(from_attributes=True)
    
    chatwoot_conversation_id: str = Field(..., description="ID of the conversation in Chatwoot")
    status: str = Field(default="pending", description="Initial status of the conversation")
    assignee_id: Optional[int] = Field(default=None, description="ID of the assigned agent")


class ConversationUpdateRequest(BaseModel):
    """Schema for API requests to update conversations."""
    model_config = ConfigDict(from_attributes=True)
    
    status: Optional[str] = Field(default=None, description="Updated status of the conversation")
    assignee_id: Optional[int] = Field(default=None, description="Updated assignee ID")
    dify_conversation_id: Optional[str] = Field(default=None, description="Updated Dify conversation ID")


class ConversationResponse(ConversationBase):
    """Schema for API responses containing conversation data."""
    id: Optional[int] = Field(default=None, description="Database ID of the conversation")
    created_at: Optional[datetime] = Field(default=None, description="Timestamp when conversation was created")
    updated_at: Optional[datetime] = Field(default=None, description="Timestamp when conversation was last updated")
    
    @computed_field
    @property
    def is_assigned(self) -> bool:
        """Check if conversation has an assigned agent."""
        return self.assignee_id is not None
    
    @computed_field
    @property
    def has_dify_integration(self) -> bool:
        """Check if conversation is integrated with Dify."""
        return self.dify_conversation_id is not None
