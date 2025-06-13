import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app
from app.schemas import ConversationResponse

load_dotenv()

# API base URL - get from environment or use default
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

# Mark all tests as asyncio
pytestmark = pytest.mark.asyncio


# Override the database dependency for testing
@pytest.fixture
def override_get_session(async_session):
    """Override the database session dependency for testing."""
    async def _get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = _get_session
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def http_client():
    """Create async HTTP client for testing API endpoints."""
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        yield client


@pytest.fixture
def test_client(override_get_session):
    """Create TestClient with dependency overrides for testing."""
    return TestClient(app)


async def test_health_endpoint():
    """Test the health check endpoint."""
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "ok"]


async def test_webhook_endpoint_with_valid_payload(chatwoot_webhook_factory):
    """Test the webhook endpoint with a valid webhook payload."""
    # Create a valid webhook payload using the factory
    webhook_payload = chatwoot_webhook_factory(
        event="message_created",
        message_type="incoming",
        content="Test message from automated test. Acknowledge receiving by saying `I see a test message`",
        conversation_id=int(os.getenv("TEST_CONVERSATION_ID", "20")),
        sender_id=123
    )

    # Convert to dict for HTTP request
    payload_dict = webhook_payload.model_dump()

    # Send webhook request
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        response = await client.post("/chatwoot-webhook", json=payload_dict)
        # We expect 200 OK even if message processing is in background
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


async def test_webhook_endpoint_with_invalid_payload():
    """Test the webhook endpoint with invalid payload for error handling."""
    invalid_payload = {
        "invalid_field": "invalid_value"
    }

    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        response = await client.post("/chatwoot-webhook", json=invalid_payload)
        # Should return validation error
        assert response.status_code == 422  # Unprocessable Entity


async def test_webhook_endpoint_with_outgoing_message(chatwoot_webhook_factory):
    """Test that outgoing messages are handled differently."""
    webhook_payload = chatwoot_webhook_factory(
        event="message_created",
        message_type="outgoing",
        content="This is an outgoing message",
        conversation_id=123,
        sender_id=456
    )

    payload_dict = webhook_payload.model_dump()
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        response = await client.post("/chatwoot-webhook", json=payload_dict)
        assert response.status_code == 200


async def test_update_labels_endpoint(test_conversation_id):
    """Test updating labels via API endpoint."""
    test_labels = ["test-label-1", "test-label-2"]

    with patch('app.api.chatwoot.ChatwootHandler') as mock_handler:
        # Mock the add_labels method
        mock_instance = AsyncMock()
        mock_instance.add_labels.return_value = {"status": "success", "labels": test_labels}
        mock_handler.return_value = mock_instance

        async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
            response = await client.post(f"/update-labels/{test_conversation_id}", json=test_labels)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "labels" in data


async def test_toggle_priority_endpoint(test_conversation_id):
    """Test toggling priority via API endpoint."""
    priority_payload = {"priority": "medium"}

    with patch('app.api.chatwoot.ChatwootHandler') as mock_handler:
        # Mock the toggle_priority method
        mock_instance = AsyncMock()
        mock_instance.toggle_priority.return_value = {"status": "success", "priority": "medium"}
        mock_handler.return_value = mock_instance

        async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
            response = await client.post(f"/toggle-priority/{test_conversation_id}", json=priority_payload)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "priority" in data


async def test_custom_attributes_endpoint(test_conversation_id):
    """Test updating custom attributes via API endpoint."""
    attributes = {"test_key": "test_value", "region": "Test Region"}

    with patch('app.api.chatwoot.ChatwootHandler') as mock_handler:
        # Mock the update_custom_attributes method
        mock_instance = AsyncMock()
        mock_instance.update_custom_attributes.return_value = {"status": "success", "custom_attributes": attributes}
        mock_handler.return_value = mock_instance

        async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
            response = await client.post(f"/update-custom-attributes/{test_conversation_id}", json=attributes)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "custom_attributes" in data


async def test_conversation_creation_endpoint(test_client, conversation_create_factory):
    """Test creating a conversation via API endpoint."""
    conversation_data = conversation_create_factory(
        chatwoot_conversation_id="api_test_123",
        status="pending"
    )

    response = test_client.post("/conversations", json=conversation_data.model_dump())
    assert response.status_code == 200
    data = response.json()
    
    # Validate response structure matches ConversationResponse schema
    conversation_response = ConversationResponse.model_validate(data)
    assert conversation_response.chatwoot_conversation_id == "api_test_123"
    assert conversation_response.status == "pending"
    assert conversation_response.id is not None


async def test_conversation_retrieval_endpoint(test_client, sample_conversation):
    """Test retrieving a conversation via API endpoint."""
    response = test_client.get(f"/conversations/{sample_conversation.chatwoot_conversation_id}")
    assert response.status_code == 200
    data = response.json()
    
    # Validate response structure
    conversation_response = ConversationResponse.model_validate(data)
    assert conversation_response.chatwoot_conversation_id == sample_conversation.chatwoot_conversation_id


async def test_conversation_update_endpoint(test_client, sample_conversation):
    """Test updating a conversation via API endpoint."""
    update_data = {
        "status": "resolved",
        "assignee_id": 456
    }

    response = test_client.patch(f"/conversations/{sample_conversation.chatwoot_conversation_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    
    # Validate response
    conversation_response = ConversationResponse.model_validate(data)
    assert conversation_response.status == "resolved"
    assert conversation_response.assignee_id == 456


async def test_error_handling_invalid_conversation_id(test_client):
    """Test error handling for invalid conversation IDs."""
    response = test_client.get("/conversations/nonexistent_id")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


async def test_webhook_validation_errors():
    """Test various webhook validation scenarios."""
    # Test missing required fields
    incomplete_payload = {
        "event": "message_created"
        # Missing message_type and other required fields
    }
    
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        response = await client.post("/chatwoot-webhook", json=incomplete_payload)
        assert response.status_code == 422
        
        # Test invalid message_type
        invalid_message_type_payload = {
            "event": "message_created",
            "message_type": "invalid_type",
            "content": "Test message"
        }
        
        response = await client.post("/chatwoot-webhook", json=invalid_message_type_payload)
        assert response.status_code == 422


async def test_endpoint_timeout_handling():
    """Test that endpoints handle timeouts gracefully."""
    # This test should verify timeout handling in webhook processing
    # For now, we just ensure the endpoint responds appropriately
    webhook_payload = {
        "event": "message_created",
        "message_type": "incoming",
        "content": "Test timeout handling",
        "conversation": {"id": 123, "status": "pending"},
        "sender": {"id": 456, "type": "contact"}
    }
    
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        response = await client.post("/chatwoot-webhook", json=webhook_payload)
        # Should not timeout and should return appropriate response
        assert response.status_code in [200, 422]  # Either success or validation error
