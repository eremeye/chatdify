import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chatwoot import ChatwootHandler
from app.db.session import async_engine, get_session

router = APIRouter()
logger = logging.getLogger(__name__)

chatwoot = ChatwootHandler()


@router.get("", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for the API using optimized database connection."""
    try:
        # Use proper async connection pattern with SQLAlchemy 2.x
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            # Fetch the result to ensure connection is working
            value = result.scalar()

        return {
            "status": "healthy", 
            "database": "connected", 
            "timestamp": time.time(),
            "db_value": value
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Health check failed: {str(e)}"
        ) from e


@router.post("/test-conversation")
async def create_test_conversation(db: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
    """
    Creates a test conversation in Chatwoot for testing purposes.
    This endpoint is for development and testing only.
    Uses proper async session management.
    """
    try:
        # Create a test conversation through Chatwoot API
        # This would be a real conversation that the system can interact with
        # Implementation will depend on the available Chatwoot API endpoints

        # Example implementation - this would need to be adjusted based on
        # available Chatwoot endpoints for creating conversations
        test_message = f"Test message created at {time.time()} Acknowledge receiving by saying `I see a test message`"

        # For now, we'll just try to get some existing conversations to verify API works
        conversations = await chatwoot.get_conversation_list()

        if conversations and len(conversations) > 0:
            # If conversations exist, use the first one for testing
            test_conversation_id = conversations[0].get("id")

            # Send a test message to this conversation
            result = await chatwoot.send_message(
                conversation_id=test_conversation_id,
                message=f"Health check: {test_message}",
                private=True,  # Use private so it doesn't disturb real users
            )

            return {
                "status": "success",
                "conversation_id": test_conversation_id,
                "message": (
                    "Test message sent to existing conversation Acknowledge receiving by saying `I see a test message`"
                ),
                "result": result,
                "timestamp": time.time(),
            }
        else:
            # In a real implementation, we would create a new conversation here
            return {
                "status": "warning",
                "message": "No existing conversations found to test with",
                "note": "Creating new conversations requires additional Chatwoot API endpoints",
                "timestamp": time.time(),
            }
    except Exception as e:
        logger.error(f"Failed to create test conversation: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create test conversation: {str(e)}"
        ) from e
