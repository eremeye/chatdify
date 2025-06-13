import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.chatwoot import ChatwootHandler
from app.config import CHATWOOT_ACCOUNT_ID, CHATWOOT_API_KEY, CHATWOOT_API_URL
from app.db.base import Base
from app.db.models import Conversation
from app.schemas import (
    ChatwootConversation,
    ChatwootMeta,
    ChatwootSender,
    ChatwootWebhook,
    ConversationCreate,
    ConversationResponse,
)

# Load environment variables
load_dotenv()


# Create an in-memory async database for testing
@pytest_asyncio.fixture(scope="session")
async def test_async_engine():
    """Create async test engine with in-memory SQLite database."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,  # Set to True for SQL debugging
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def create_tables(test_async_engine):
    """Create all database tables for testing."""
    # Import models to register them with metadata
    import app.db.models  # noqa: F401
    
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Clean up after tests
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_session(test_async_engine, create_tables) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide async database session for tests with proper transaction handling.
    Each test gets a fresh transaction that is rolled back after the test.
    """
    async with AsyncSession(test_async_engine) as session:
        # Start a transaction
        trans = await session.begin()
        try:
            yield session
        finally:
            # Always rollback to ensure test isolation
            # Check if transaction is still active before rolling back
            if trans.is_active:
                await trans.rollback()
            # Close the session
            await session.close()


@pytest.fixture
def chatwoot_handler():
    """Create ChatwootHandler instance for testing."""
    return ChatwootHandler(
        api_url=CHATWOOT_API_URL,
        api_key=CHATWOOT_API_KEY,
        account_id=CHATWOOT_ACCOUNT_ID,
    )


@pytest.fixture
def test_conversation_id():
    """Provide test conversation ID for Chatwoot integration tests."""
    return int(os.getenv("TEST_CONVERSATION_ID", "20"))


# Test data factories
@pytest.fixture
def conversation_factory():
    """Factory for creating test Conversation models."""
    def _create_conversation(
        chatwoot_conversation_id: str = "123",
        status: str = "pending",
        assignee_id: int = None,
        dify_conversation_id: str = None,
        **kwargs
    ) -> Conversation:
        return Conversation(
            chatwoot_conversation_id=chatwoot_conversation_id,
            status=status,
            assignee_id=assignee_id,
            dify_conversation_id=dify_conversation_id,
            **kwargs
        )
    return _create_conversation


@pytest.fixture
def conversation_create_factory():
    """Factory for creating ConversationCreate Pydantic schemas."""
    def _create_conversation_create(
        chatwoot_conversation_id: str = "123",
        status: str = "pending",
        assignee_id: int = None,
        dify_conversation_id: str = None,
        **kwargs
    ) -> ConversationCreate:
        return ConversationCreate(
            chatwoot_conversation_id=chatwoot_conversation_id,
            status=status,
            assignee_id=assignee_id,
            dify_conversation_id=dify_conversation_id,
            **kwargs
        )
    return _create_conversation_create


@pytest.fixture
def chatwoot_webhook_factory():
    """Factory for creating ChatwootWebhook test data."""
    def _create_webhook(
        event: str = "message_created",
        message_type: str = "incoming",
        content: str = "Test message",
        conversation_id: int = 123,
        sender_id: int = 456,
        **kwargs
    ) -> ChatwootWebhook:
        return ChatwootWebhook(
            event=event,
            message_type=message_type,
            content=content,
            sender=ChatwootSender(id=sender_id, type="contact"),
            conversation=ChatwootConversation(
                id=conversation_id,
                status="pending",
                meta=ChatwootMeta(assignee=None)
            ),
            **kwargs
        )
    return _create_webhook


@pytest.fixture
def mock_chatwoot_handler():
    """Create a mock ChatwootHandler for testing without external API calls."""
    handler = AsyncMock(spec=ChatwootHandler)
    
    # Configure common mock responses
    handler.get_teams.return_value = [{"id": 1, "name": "Test Team"}]
    handler.send_message.return_value = {"id": 123, "content": "Test response"}
    handler.get_conversation_data.return_value = {
        "id": 123,
        "status": "open",
        "priority": "medium",
        "labels": [],
        "custom_attributes": {}
    }
    handler.toggle_status.return_value = {"status": "success"}
    handler.add_labels.return_value = {"status": "success"}
    handler.update_custom_attributes.return_value = {"status": "success"}
    handler.toggle_priority.return_value = {"status": "success"}
    
    return handler


@pytest_asyncio.fixture
async def wait_for_service():
    """Fixture to wait for a service to be available with proper async handling."""
    async def _wait(check_func, timeout=5, interval=2):
        """
        Wait for a service to be available

        Args:
            check_func: Async function that returns True if service is available
            timeout: Maximum time to wait in seconds
            interval: Time between checks in seconds

        Returns:
            True if service became available, False if timeout was reached
        """
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                if await check_func():
                    return True
            except Exception:
                pass
            await asyncio.sleep(interval)
        return False

    return _wait


# Database utility fixtures
@pytest_asyncio.fixture
async def sample_conversation(async_session: AsyncSession, conversation_factory) -> Conversation:
    """Create a sample conversation in the test database."""
    conversation = conversation_factory(
        chatwoot_conversation_id="test_123",
        status="pending"
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)
    return conversation


@pytest_asyncio.fixture
async def multiple_conversations(async_session: AsyncSession, conversation_factory) -> list[Conversation]:
    """Create multiple test conversations in the database."""
    conversations = [
        conversation_factory(chatwoot_conversation_id="conv_1", status="pending"),
        conversation_factory(chatwoot_conversation_id="conv_2", status="open"),
        conversation_factory(chatwoot_conversation_id="conv_3", status="resolved"),
    ]
    
    for conv in conversations:
        async_session.add(conv)
    
    await async_session.commit()
    
    for conv in conversations:
        await async_session.refresh(conv)
    
    return conversations
