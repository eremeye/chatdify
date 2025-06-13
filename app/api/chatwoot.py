"""Chatwoot API endpoints with SQLAlchemy 2 and Pydantic v2 integration."""
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app import config
from app.db.session import get_session
from app.models import Conversation, ConversationCreate, ConversationResponse

logger = logging.getLogger(__name__)

# Create router for Chatwoot API endpoints
router = APIRouter(prefix="/chatwoot", tags=["chatwoot"])


class ChatwootHandler:
    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        account_id: str | None = None,
        admin_api_key: str | None = None,
    ):
        self.api_url = api_url or config.CHATWOOT_API_URL
        self.account_id = account_id or config.CHATWOOT_ACCOUNT_ID
        self.api_key = api_key or config.CHATWOOT_API_KEY
        self.admin_api_key = admin_api_key or config.CHATWOOT_ADMIN_API_KEY
        self.headers = {
            "api_access_token": self.api_key,
            "Content-Type": "application/json",
        }
        self.admin_headers = {
            "api_access_token": self.admin_api_key,
            "Content-Type": "application/json",
        }
        # Base URLs
        self.account_url = f"{self.api_url}/accounts/{self.account_id}"
        self.conversations_url = f"{self.account_url}/conversations"

    def send_message_sync(self, conversation_id: int, message: str, private: bool = False):
        """Synchronous version of send_message for use in Celery tasks"""
        import httpx

        url = f"{self.conversations_url}/{conversation_id}/messages"

        data = {
            "content": message,
            "message_type": "outgoing",
            "private": private,
        }

        with httpx.Client() as client:
            response = client.post(url, json=data, headers=self.headers, timeout=30.0)
            response.raise_for_status()
            return response.json()

    async def send_message(
        self,
        conversation_id: int,
        message: str,
        private: bool = False,
        attachments: List[str] | None = None,
        content_attributes: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Send a message or private note to a conversation with rich content support"""
        url = f"{self.conversations_url}/{conversation_id}/messages"
        data = {
            "content": message,
            "message_type": "outgoing",
            "private": private,
            "content_attributes": content_attributes or {},
        }

        if attachments:
            data["attachments"] = [{"url": url} for url in attachments]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to send message to conversation {conversation_id}: {e}")
            raise

    async def add_labels(self, conversation_id: int, labels: List[str]) -> Dict[str, Any]:
        """Add labels to a conversation"""
        url = f"{self.conversations_url}/{conversation_id}/labels"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json={"labels": labels}, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to add labels to conversation {conversation_id}: {e}")
            raise

    async def get_conversation_data(self, conversation_id: int) -> Dict[str, Any]:
        """Get conversation data including custom attributes and labels"""
        url = f"{self.conversations_url}/{conversation_id}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.admin_headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Get conversation failed for {conversation_id}:\n"
                f"URL: {url}\nStatus: {e.response.status_code}\n"
                f"Response: {e.response.text}",
                exc_info=True,
            )
            raise

    async def assign_conversation(self, conversation_id: int, assignee_id: int) -> Dict[str, Any]:
        """Assign a conversation to an agent."""
        url = f"{self.conversations_url}/{conversation_id}/assignments"
        data = {"assignee_id": assignee_id}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to assign conversation {conversation_id} to agent {assignee_id}: {e}")
            raise

    async def update_custom_attributes(self, conversation_id: int, custom_attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Update custom attributes for a conversation using the provided account_id and conversation_id."""
        custom_attrs_url = f"{self.conversations_url}/{conversation_id}/custom_attributes"

        try:
            async with httpx.AsyncClient() as client:
                payload = {"custom_attributes": custom_attributes}

                # Use POST to update attributes
                response = await client.post(custom_attrs_url, json=payload, headers=self.headers)
                response.raise_for_status()
                if response.content and len(response.content.strip()) > 0:
                    try:
                        return response.json()
                    except Exception as json_err:
                        logger.warning(f"Failed to parse JSON response: {json_err}")
                        return {}
                return {}
        except Exception as e:
            logger.error(f"Failed to update custom attributes for conversation {conversation_id}: {e}")
            raise

    async def toggle_priority(self, conversation_id: int, priority: str) -> Dict[str, Any]:
        """Toggle the priority of a conversation
        Valid priorities: 'urgent', 'high', 'medium', 'low', None
        """
        url = f"{self.conversations_url}/{conversation_id}/toggle_priority"
        data = {"priority": priority}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=self.headers)
                response.raise_for_status()
                if response.content and len(response.content.strip()) > 0:
                    try:
                        return response.json()
                    except Exception as json_err:
                        logger.warning(f"Failed to parse JSON response: {json_err}")
                        return {}
                return {}
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Priority update failed for conversation {conversation_id}:\n"
                f"URL: {url}\nStatus: {e.response.status_code}\n"
                f"Response: {e.response.text}\nPriority: {priority}",
                exc_info=True,
            )
            raise

    async def assign_team(
        self, conversation_id: int, team_id: int = 0, team_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Assign a conversation to a team.

        Args:
            conversation_id: The ID of the conversation to assign
            team_id: The ID of the team to assign to
            team_name: The name of the team to assign to (will be looked up if provided)
        """
        url = f"{self.conversations_url}/{conversation_id}/assignments"

        # Use team name to get team_id if provided
        if team_name and not team_id:
            teams = await self.get_teams()
            team_map = {team["name"].lower(): team["id"] for team in teams}
            team_id = team_map.get(team_name.lower(), 0)

        data = {"team_id": team_id}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to assign conversation {conversation_id} to team {team_id}: {e}")
            raise

    async def create_custom_attribute_definition(
        self,
        display_name: str,
        attribute_key: str,
        attribute_values: List[str],
        description: str = "",
        attribute_model: int = 0,
    ) -> Dict[str, Any]:
        """Create a custom attribute definition"""
        url = f"{self.api_url}/platform/accounts/{self.account_id}/custom_attribute_definitions"

        data = {
            "custom_attribute": {
                "attribute_display_name": display_name,
                "attribute_key": attribute_key,
                "attribute_values": attribute_values,
                "attribute_description": description,
                "attribute_model": attribute_model,
                "attribute_display_type": 1,
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=self.admin_headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to create custom attribute definition: {e}")
            raise

    async def toggle_status(
        self,
        conversation_id: int,
        status: str,
        previous_status: Optional[str] = None,
        is_error_transition: bool = False,
    ) -> Dict[str, Any]:
        """Toggle the status of a conversation
        Valid statuses: 'open', 'resolved', 'pending', 'snoozed'
        """
        url = f"{self.conversations_url}/{conversation_id}/toggle_status"
        data = {"status": status}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=self.headers)
                response.raise_for_status()
                if response.content and len(response.content.strip()) > 0:
                    try:
                        return response.json()
                    except Exception as json_err:
                        logger.warning(f"Failed to parse JSON response: {json_err}")
                        return {}
                return {}
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Status toggle failed for conversation {conversation_id}:\n"
                f"URL: {url}\nStatus: {e.response.status_code}\n"
                f"Response: {e.response.text}\nNew status: {status}",
                exc_info=True,
            )
            raise

    def toggle_status_sync(
        self,
        conversation_id: int,
        status: str,
        previous_status: Optional[str] = None,
        is_error_transition: bool = False,
    ) -> Dict[str, Any]:
        """Synchronous version of toggle_status for use in Celery tasks"""
        import httpx

        url = f"{self.conversations_url}/{conversation_id}/toggle_status"
        data = {"status": status}

        try:
            with httpx.Client() as client:
                response = client.post(url, json=data, headers=self.headers, timeout=30.0)
                response.raise_for_status()
                if response.content and len(response.content.strip()) > 0:
                    try:
                        return response.json()
                    except Exception as json_err:
                        logger.warning(f"Failed to parse JSON response: {json_err}")
                        return {}
                return {}
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Status toggle (sync) failed for conversation {conversation_id}:\n"
                f"URL: {url}\nStatus: {e.response.status_code}\n"
                f"Response: {e.response.text}\nNew status: {status}",
                exc_info=True,
            )
            raise

    async def get_teams(self) -> List[Dict[str, Any]]:
        """Get all teams for the account"""
        url = f"{self.account_url}/teams"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()

                # Safely extract teams from nested structure
                if isinstance(data, dict) and "payload" in data:
                    teams = data["payload"]
                elif isinstance(data, list):
                    teams = data
                else:
                    teams = []

                logger.info(f"Retrieved {len(teams)} teams from Chatwoot")
                return teams

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Get teams failed:\n"
                f"URL: {url}\nStatus: {e.response.status_code}\n"
                f"Response: {e.response.text}",
                exc_info=True,
            )
            return []
        except Exception as e:
            logger.error(f"Failed to get teams: {e}")
            return []

    async def get_conversation_list(self, status: str = "all", assignee_type: str = "all") -> List[Dict[str, Any]]:
        """Get list of conversations with optional filtering"""
        url = f"{self.conversations_url}"
        params = {
            "status": status,
            "assignee_type": assignee_type,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                data = response.json()

                # Extract conversations from response
                if isinstance(data, dict) and "data" in data and "payload" in data["data"]:
                    conversations = data["data"]["payload"]
                elif isinstance(data, list):
                    conversations = data
                else:
                    conversations = []

                logger.info(f"Retrieved {len(conversations)} conversations from Chatwoot")
                return conversations

        except Exception as e:
            logger.error(f"Failed to get conversation list: {e}")
            return []


# Global handler instance
chatwoot = ChatwootHandler()


# FastAPI endpoints demonstrating new patterns

@router.get("/conversations")
async def get_conversations(
    limit: int = Query(default=10, le=100, description="Number of conversations to return"),
    offset: int = Query(default=0, ge=0, description="Number of conversations to skip"),
    status: Optional[str] = Query(default=None, description="Filter by conversation status"),
    db: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Get conversations with proper SQLAlchemy 2.x query optimization and Pydantic v2 serialization.
    
    Demonstrates:
    - SQLAlchemy 2.x select() syntax
    - Proper pagination
    - Optional filtering
    - Pydantic v2 model_validate with from_attributes
    """
    # Build query with SQLAlchemy 2.x syntax
    query = select(Conversation)
    
    # Add optional status filter
    if status:
        query = query.where(Conversation.status == status)
    
    # Add pagination
    query = query.offset(offset).limit(limit)
    
    # For larger datasets with relationships, we would use eager loading:
    # query = query.options(selectinload(Conversation.messages))  # if we had a messages relationship
    
    # Execute query
    result = await db.execute(query)
    conversations = result.scalars().all()
    
    # Count total for pagination info
    count_result = await db.execute(select(Conversation).where(
        Conversation.status == status if status else True
    ))
    total = len(count_result.scalars().all())
    
    # Use Pydantic v2 model_validate with from_attributes for proper serialization
    conversation_responses = [
        ConversationResponse.model_validate(conv, from_attributes=True) 
        for conv in conversations
    ]
    
    return {
        "conversations": [conv.model_dump() for conv in conversation_responses],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": (offset + limit) < total
        }
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    """
    Get a single conversation by ID with optimized query and proper response serialization.
    
    Demonstrates:
    - Single item query optimization
    - Proper error handling
    - Pydantic v2 response serialization
    """
    # Use SQLAlchemy 2.x select syntax
    # For relationships, we might use joinedload for 1-to-1 or small 1-to-few:
    # query = select(Conversation).options(joinedload(Conversation.assignee)).where(...)
    # Or selectinload for larger child sets:
    # query = select(Conversation).options(selectinload(Conversation.messages)).where(...)
    
    query = select(Conversation).where(Conversation.chatwoot_conversation_id == conversation_id)
    result = await db.execute(query)
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Use Pydantic v2 model_validate with from_attributes for proper serialization
    return ConversationResponse.model_validate(conversation, from_attributes=True)


@router.post("/conversations")
async def create_conversation(
    conversation_data: ConversationCreate,
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    """
    Create a new conversation with proper Pydantic v2 validation and serialization.
    
    Demonstrates:
    - Pydantic v2 request validation
    - SQLAlchemy 2.x model creation
    - Proper response serialization
    """
    # Use Pydantic model_dump for safe data extraction
    conversation_dict = conversation_data.model_dump(exclude={'id'})
    
    # Create SQLAlchemy model instance
    conversation = Conversation(**conversation_dict)
    
    # Add and commit
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    
    # Use Pydantic v2 model_validate with from_attributes for response
    return ConversationResponse.model_validate(conversation, from_attributes=True)
