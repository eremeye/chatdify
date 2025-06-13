"""Test utilities and helper functions for the updated test suite."""
import random
import string
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation
from app.schemas import (
    ChatwootConversation,
    ChatwootMeta,
    ChatwootSender,
    ChatwootWebhook,
    ConversationCreate,
    ConversationResponse,
)


def generate_random_string(length: int = 10) -> str:
    """Generate a random string for testing purposes."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_test_email(prefix: str = "test") -> str:
    """Generate a test email address."""
    return f"{prefix}_{generate_random_string(8)}@example.com"


async def create_test_conversation(
    async_session: AsyncSession,
    chatwoot_conversation_id: Optional[str] = None,
    status: str = "pending",
    **kwargs
) -> Conversation:
    """Create a test conversation in the database."""
    if not chatwoot_conversation_id:
        chatwoot_conversation_id = f"test_conv_{generate_random_string(8)}"
    
    conversation_data = ConversationCreate(
        chatwoot_conversation_id=chatwoot_conversation_id,
        status=status,
        **kwargs
    )
    
    conversation = Conversation(**conversation_data.model_dump())
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)
    return conversation


async def get_conversation_by_chatwoot_id(
    async_session: AsyncSession,
    chatwoot_conversation_id: str
) -> Optional[Conversation]:
    """Get conversation by Chatwoot conversation ID."""
    statement = select(Conversation).where(
        Conversation.chatwoot_conversation_id == chatwoot_conversation_id
    )
    result = await async_session.execute(statement)
    return result.scalar_one_or_none()


async def cleanup_test_conversations(
    async_session: AsyncSession,
    chatwoot_conversation_ids: list[str]
):
    """Clean up test conversations from the database."""
    for conv_id in chatwoot_conversation_ids:
        conversation = await get_conversation_by_chatwoot_id(async_session, conv_id)
        if conversation:
            await async_session.delete(conversation)
    await async_session.commit()


def create_mock_chatwoot_handler() -> AsyncMock:
    """Create a mock ChatwootHandler with standard responses."""
    handler = AsyncMock()
    
    # Default mock responses
    handler.get_teams.return_value = [
        {"id": 1, "name": "Support Team"},
        {"id": 2, "name": "Sales Team"}
    ]
    
    handler.send_message.return_value = {
        "id": 123,
        "content": "Mock response",
        "created_at": "2024-01-01T00:00:00Z"
    }
    
    handler.get_conversation_data.return_value = {
        "id": 123,
        "status": "open",
        "priority": "medium",
        "labels": [],
        "custom_attributes": {},
        "meta": {"team": {"name": "Support Team"}}
    }
    
    handler.toggle_status.return_value = {"status": "success"}
    handler.add_labels.return_value = {"status": "success"}
    handler.update_custom_attributes.return_value = {"status": "success"}
    handler.toggle_priority.return_value = {"status": "success"}
    
    return handler


def create_test_webhook_payload(
    event: str = "message_created",
    message_type: str = "incoming",
    content: str = "Test message",
    conversation_id: int = 123,
    sender_id: int = 456,
    **kwargs
) -> Dict[str, Any]:
    """Create a test webhook payload."""
    return {
        "event": event,
        "message_type": message_type,
        "content": content,
        "conversation": {
            "id": conversation_id,
            "status": "open",
            "meta": {"assignee": None}
        },
        "sender": {
            "id": sender_id,
            "type": "contact"
        },
        **kwargs
    }


def assert_conversation_response_valid(response_data: Dict[str, Any]):
    """Assert that a conversation response has valid structure."""
    assert "id" in response_data
    assert "chatwoot_conversation_id" in response_data
    assert "status" in response_data
    assert "created_at" in response_data
    assert "updated_at" in response_data
    
    # Validate using Pydantic schema
    ConversationResponse.model_validate(response_data)


def assert_webhook_payload_valid(payload: Dict[str, Any]):
    """Assert that a webhook payload has valid structure."""
    assert "event" in payload
    assert "message_type" in payload
    
    # Validate using Pydantic schema
    ChatwootWebhook.model_validate(payload)


async def assert_database_conversation_exists(
    async_session: AsyncSession,
    chatwoot_conversation_id: str,
    expected_status: Optional[str] = None
) -> Conversation:
    """Assert that a conversation exists in the database with expected properties."""
    conversation = await get_conversation_by_chatwoot_id(async_session, chatwoot_conversation_id)
    assert conversation is not None, f"Conversation {chatwoot_conversation_id} not found in database"
    
    if expected_status:
        assert conversation.status == expected_status, f"Expected status {expected_status}, got {conversation.status}"
    
    return conversation


def create_test_scenarios() -> Dict[str, Dict[str, Any]]:
    """Create standardized test scenarios for integration tests."""
    return {
        "basic_support_inquiry": {
            "messages": [
                {"role": "user", "text": "I need help with my account"},
                {"role": "assistant", "text": "I'll help you with your account issue"}
            ],
            "expected_attributes": {
                "priority": "medium",
                "team": "Support Team",
                "region": "US"
            }
        },
        "billing_question": {
            "messages": [
                {"role": "user", "text": "I have a question about my bill"},
                {"role": "assistant", "text": "Let me help you with your billing question"}
            ],
            "expected_attributes": {
                "priority": "high",
                "team": "Billing Team",
                "category": "billing"
            }
        },
        "technical_issue": {
            "messages": [
                {"role": "user", "text": "The app is crashing when I try to login"},
                {"role": "assistant", "text": "I'll help you troubleshoot this technical issue"}
            ],
            "expected_attributes": {
                "priority": "high", 
                "team": "Tech Support",
                "issue_type": "technical"
            }
        }
    }


class TestDataBuilder:
    """Builder class for creating test data with fluent interface."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset builder to initial state."""
        self._data = {}
        return self
    
    def with_conversation_id(self, conv_id: str):
        """Set conversation ID."""
        self._data["chatwoot_conversation_id"] = conv_id
        return self
    
    def with_status(self, status: str):
        """Set conversation status."""
        self._data["status"] = status
        return self
    
    def with_assignee(self, assignee_id: int):
        """Set assignee ID."""
        self._data["assignee_id"] = assignee_id
        return self
    
    def with_dify_id(self, dify_id: str):
        """Set Dify conversation ID."""
        self._data["dify_conversation_id"] = dify_id
        return self
    
    def build_conversation_create(self) -> ConversationCreate:
        """Build ConversationCreate schema."""
        return ConversationCreate(**self._data)
    
    def build_conversation_model(self) -> Conversation:
        """Build Conversation model."""
        return Conversation(**self._data)
    
    def build_webhook(
        self,
        event: str = "message_created",
        message_type: str = "incoming",
        content: str = "Test message"
    ) -> ChatwootWebhook:
        """Build ChatwootWebhook schema."""
        conv_id = self._data.get("chatwoot_conversation_id", "123")
        return ChatwootWebhook(
            event=event,
            message_type=message_type,
            content=content,
            sender=ChatwootSender(id=456, type="contact"),
            conversation=ChatwootConversation(
                id=int(conv_id) if conv_id.isdigit() else 123,
                status=self._data.get("status", "open"),
                meta=ChatwootMeta(assignee=None)
            )
        ) 