import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app import tasks
from app.api.chatwoot import ChatwootHandler
from app.config import (
    BOT_CONVERSATION_OPENED_MESSAGE_EXTERNAL,
    BOT_ERROR_MESSAGE_INTERNAL,
    ENABLE_TEAM_CACHE,
    TEAM_CACHE_TTL_HOURS,
)
from app.db.models import Conversation
from app.db.session import get_session
from app.db.utils import create_db_tables
from app.schemas import (
    ChatwootWebhook,
    ConversationCreate,
    ConversationPriority,
    ConversationResponse,
    ConversationStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter()
chatwoot = ChatwootHandler()

# Team management - only initialize if caching is enabled
team_cache: Dict[str, int] = {} if ENABLE_TEAM_CACHE else {}
team_cache_lock = asyncio.Lock() if ENABLE_TEAM_CACHE else None
last_update_time = 0


async def get_or_create_conversation(db: AsyncSession, data: ConversationCreate) -> Conversation:
    """
    Get existing conversation or create a new one.
    Updates the conversation if it exists with new data.
    """
    statement = select(Conversation).where(Conversation.chatwoot_conversation_id == data.chatwoot_conversation_id)
    result = await db.execute(statement)
    conversation = result.scalar_one_or_none()

    if conversation:
        # Update existing conversation with new data
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(conversation, field, value)
        conversation.updated_at = datetime.now(UTC)
    else:
        # Create new conversation
        conversation = Conversation(**data.model_dump())
        db.add(conversation)

    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.post("/send-chatwoot-message")
async def send_chatwoot_message(
    conversation_id: int,
    message: str,
    is_private: bool = False,
    db: AsyncSession = Depends(get_session),
):
    """
    Send a message to Chatwoot conversation.
    Can be used as a private note if is_private=True
    """
    try:
        # For private notes, we need to set both private=True and message_type="private"
        await chatwoot.send_message(
            conversation_id=conversation_id,
            message=message,
            private=is_private,
        )
        return {"status": "success", "message": "Message sent successfully"}
    except Exception as e:
        logger.error(f"Failed to send message to Chatwoot: {e}")
        raise HTTPException(status_code=500, detail="Failed to send message to Chatwoot") from e


@router.post("/chatwoot-webhook")
async def chatwoot_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    print("Received Chatwoot webhook request")
    payload = await request.json()
    webhook_data = ChatwootWebhook.model_validate(payload)

    logger.info(f"Received webhook event: {webhook_data.event}")
    logger.debug(f"Webhook payload: {payload}")

    if webhook_data.event == "message_created":
        logger.info(f"Webhook data: {webhook_data}")
        if webhook_data.sender_type in [
            "agent_bot",
            "????",
        ]:  # бот не реагирует на свои мессаги
            logger.info(f"Skipping agent_bot message: {webhook_data.content}")
            return {"status": "skipped", "reason": "agent_bot message"}
        # conversation_is_open = webhook_data.status == "open"
        # user_messages_when_pending = webhook_data.status == "pending" and webhook_data.message_type == "incoming"
        # if not webhook_data.message:
        #     logger.info(f"Skipping message with empty content: {webhook_data}")
        #     return {"status": "skipped", "reason": "empty message"}
        if str(webhook_data.content).startswith(BOT_CONVERSATION_OPENED_MESSAGE_EXTERNAL) or str(
            webhook_data.content
        ).startswith(BOT_ERROR_MESSAGE_INTERNAL):
            logger.info(f"Skipping agent_bot message: {webhook_data.content}")
            return {"status": "skipped", "reason": "agent_bot message"}

        if True:  # we'll see if we need to filter by status later
            print(f"Processing message: {webhook_data}")
            try:
                conversation_data = webhook_data.to_conversation_create()
                conversation = await get_or_create_conversation(db, conversation_data)

                # Just start the task and return immediately

                # https://github.com/langgenius/dify/issues/11140 IMPORTANT : `inputs` are cached for conversation
                tasks.process_message_with_dify.apply_async(
                    args=[
                        webhook_data.content,
                        conversation.dify_conversation_id,
                        conversation.chatwoot_conversation_id,
                        conversation.status,
                        webhook_data.message_type,
                    ],
                    link=tasks.handle_dify_response.s(
                        conversation_id=webhook_data.conversation_id,
                    ),
                    link_error=tasks.handle_dify_error.s(
                        conversation_id=webhook_data.conversation_id,
                    ),
                )

                return {"status": "processing"}

            except Exception as e:
                logger.error(f"Failed to process message with Dify: {e}")
                if webhook_data.conversation_id is not None:
                    await send_chatwoot_message(
                        conversation_id=webhook_data.conversation_id,
                        message=BOT_CONVERSATION_OPENED_MESSAGE_EXTERNAL,
                        is_private=False,
                        db=db,
                    )
                else:
                    logger.error(
                        "Cannot send error message: conversation_id is "
                        f"None in webhook data for event {webhook_data.event}"
                    )

    elif webhook_data.event == "conversation_created":
        if not webhook_data.conversation:
            return {"status": "skipped", "reason": "no conversation data"}

        conversation_data = webhook_data.to_conversation_create()
        conversation = await get_or_create_conversation(db, conversation_data)
        return {"status": "success", "conversation_id": conversation.id}

    elif webhook_data.event == "conversation_updated":
        if not webhook_data.conversation:
            return {"status": "skipped", "reason": "no conversation data"}

        conversation_data = webhook_data.to_conversation_create()
        conversation = await get_or_create_conversation(db, conversation_data)
        return {"status": "success", "conversation_id": conversation.id}

    elif webhook_data.event == "conversation_deleted":
        if not webhook_data.conversation:
            return {"status": "skipped", "reason": "no conversation data"}

        conversation_id = str(webhook_data.conversation.id)
        statement = select(Conversation).where(Conversation.chatwoot_conversation_id == conversation_id)
        conversation = await db.execute(statement)
        conversation = conversation.scalar_one_or_none()

        if conversation and conversation.dify_conversation_id:
            background_tasks.add_task(tasks.delete_dify_conversation, conversation.dify_conversation_id)
            await db.delete(conversation)
            await db.commit()

    return {"status": "success"}


@router.post("/update-labels/{conversation_id}")
async def update_labels(conversation_id: int, labels: List[str], db: AsyncSession = Depends(get_session)):
    """
    Update labels for a Chatwoot conversation

    Parameters:
    - conversation_id: The ID of the conversation to update (path parameter)
    - labels: List of label strings to apply to the conversation (request body)
    """
    try:
        result = await chatwoot.add_labels(conversation_id=conversation_id, labels=labels)
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "labels": result,
        }
    except Exception as e:
        logger.error(f"Failed to update labels for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update labels: {str(e)}") from e


@router.post("/update-custom-attributes/{conversation_id}")
async def update_custom_attributes(
    conversation_id: int,
    custom_attributes: Dict[str, Any],
    db: AsyncSession = Depends(get_session),
):
    """
    Update custom attributes for a Chatwoot conversation

    Parameters:
    - conversation_id: The ID of the conversation to update (path parameter)
    - custom_attributes: Dictionary of custom attributes to set (request body)

    Example request body:
    {"region": "Moscow", "region_original_string": "Moscow"}
    """
    if not isinstance(custom_attributes, dict) or not custom_attributes:
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "custom_attributes": "No custom attrs provided",
        }
    try:
        result = await chatwoot.update_custom_attributes(
            conversation_id=conversation_id, custom_attributes=custom_attributes
        )
        logger.info(f"Updated custom attributes for conversation {conversation_id}: {result}")
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "custom_attributes": result,
        }
    except Exception as e:
        # Log the full exception details including traceback
        logger.exception(f"Failed to update custom attributes for conversation {conversation_id}:")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "conversation_id": conversation_id,
                "attempted_attributes": custom_attributes,
                "traceback": f"{type(e).__name__}: {str(e)}",
            },
        ) from e


@router.post("/toggle-priority/{conversation_id}")
async def toggle_conversation_priority(
    conversation_id: int,
    priority: ConversationPriority = Body(
        ...,
        embed=True,
        description="Priority level: 'urgent', 'high', 'medium', 'low', or None",
    ),
    db: AsyncSession = Depends(get_session),
):
    """
    Toggle the priority of a Chatwoot conversation

    Parameters:
    - conversation_id: The ID of the conversation to update (path parameter)
    - priority: Priority level to set (request body)

    Example request body:
        {
            "priority": "high"
        }
    """
    try:
        priority_value = priority.value
        if not priority_value or priority_value.lower() == "none":
            return {
                "status": "success",
                "conversation_id": conversation_id,
                "priority": "None",
            }
        logger.info(f"Attempting to set priority {priority_value} for conversation {conversation_id}")
        result = await chatwoot.toggle_priority(conversation_id=conversation_id, priority=str(priority_value))
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "priority": result,
        }
    except Exception as e:
        # Log the full exception details
        logger.exception(f"Detailed error when toggling priority for conversation {conversation_id}:")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "conversation_id": conversation_id,
                "attempted_priority": str(priority_value),
            },
        ) from e


@router.get("/conversations/dify/{dify_conversation_id}")
async def get_chatwoot_conversation_id(dify_conversation_id: str, db: AsyncSession = Depends(get_session)):
    """
    Get Chatwoot conversation ID from Dify conversation ID
    """
    statement = select(Conversation).where(Conversation.dify_conversation_id == dify_conversation_id)
    conversation = await db.execute(statement)
    conversation = conversation.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"No conversation found with Dify ID: {dify_conversation_id}",
        )

    # Use ConversationResponse DTO with model_validate
    response_data = ConversationResponse.model_validate(conversation)
    return {
        "chatwoot_conversation_id": response_data.chatwoot_conversation_id,
        "status": response_data.status,
        "assignee_id": response_data.assignee_id,
        "is_assigned": response_data.is_assigned,
        "has_dify_integration": response_data.has_dify_integration,
    }


@router.get("/conversation-info/{chatwoot_conversation_id}")
async def get_conversation_info(chatwoot_conversation_id: int, db: AsyncSession = Depends(get_session)):
    """
    Retrieve conversation information, including the Dify conversation ID,
    based on the Chatwoot conversation ID. Used for testing/debugging.
    """
    logger.debug(f"Received request for conversation info for Chatwoot convo ID: {chatwoot_conversation_id}")
    statement = select(Conversation).where(Conversation.chatwoot_conversation_id == str(chatwoot_conversation_id))
    result = await db.execute(statement)
    conversation = result.scalar_one_or_none()

    if not conversation:
        logger.warning(f"Conversation not found for Chatwoot convo ID: {chatwoot_conversation_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Conversation not found for Chatwoot conversation ID {chatwoot_conversation_id}",
        )

    logger.debug(
        f"Found conversation for Chatwoot convo ID {chatwoot_conversation_id}: Dify ID = {conversation.dify_conversation_id}"
    )
    
    # Use ConversationResponse DTO with model_validate for consistent response structure
    response_data = ConversationResponse.model_validate(conversation)
    return response_data.model_dump()


async def update_team_cache():
    """Update the team name to ID mapping cache."""
    if not ENABLE_TEAM_CACHE:
        logger.warning("Team caching is disabled. Skipping cache update.")
        return {}

    global team_cache, last_update_time

    async with team_cache_lock:
        try:
            teams = await chatwoot.get_teams()

            # Create case-insensitive mappings from name to ID
            new_cache = {team["name"].lower(): team["id"] for team in teams}

            # Update the cache
            team_cache = new_cache
            last_update_time = datetime.now(UTC).timestamp()

            logger.info(f"Updated team cache with {len(team_cache)} teams")
            return team_cache
        except Exception as e:
            logger.error(f"Failed to update team cache: {e}", exc_info=True)
            raise


async def get_team_id(team_name: str) -> Optional[int]:
    """Get team ID from name, updating cache if necessary.

    Args:
        team_name: The name of the team to look up

    Returns:
        The team ID or None if not found
    """
    if not ENABLE_TEAM_CACHE:
        # Direct API call when caching is disabled
        try:
            teams = await chatwoot.get_teams()
            team_map = {team["name"].lower(): team["id"] for team in teams}
            return team_map.get(team_name.lower())
        except Exception as e:
            logger.error(f"Failed to get team ID for '{team_name}' (no cache): {e}")
            return None

    # Use cache when enabled
    cache_age_hours = (datetime.now(UTC).timestamp() - last_update_time) / 3600
    if not team_cache or cache_age_hours > TEAM_CACHE_TTL_HOURS:
        await update_team_cache()

    return team_cache.get(team_name.lower())


@router.post("/refresh-teams")
async def refresh_teams_cache():
    """Manually refresh the team cache."""
    if not ENABLE_TEAM_CACHE:
        # When caching is disabled, just return current teams from API
        try:
            teams = await chatwoot.get_teams()
            return {"status": "success", "teams": len(teams), "cache_enabled": False}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch teams: {str(e)}") from e

    try:
        teams = await update_team_cache()
        return {"status": "success", "teams": len(teams), "cache_enabled": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh teams: {str(e)}") from e


@router.post("/assign-team/{conversation_id}")
async def assign_conversation_to_team(
    conversation_id: int,
    team: str = Body(
        ...,
        embed=True,
        description="Team name to assign the conversation to",
    ),
    db: AsyncSession = Depends(get_session),
):
    """
    Assign a Chatwoot conversation to a team

    Parameters:
    - conversation_id: The ID of the conversation to update (path parameter)
    - team: Team name to assign (request body)

    Example request body:
        {
            "team": "Support"
        }
    """
    if not team or team.lower() == "none":
        return {"status": "success", "conversation_id": conversation_id, "team": "None"}
    try:
        # Log the attempt
        logger.info(f"Attempting to assign conversation {conversation_id} to team {team}")

        # Get team_id from name
        team_id = await get_team_id(team)

        if team_id is None:
            if ENABLE_TEAM_CACHE:
                # Try to refresh the cache and try again
                await update_team_cache()
                team_id = await get_team_id(team)

            if team_id is None:
                # Get available teams for error message
                try:
                    if ENABLE_TEAM_CACHE:
                        available_teams = list(team_cache.keys())
                    else:
                        teams = await chatwoot.get_teams()
                        available_teams = [team["name"].lower() for team in teams]
                except Exception:
                    available_teams = ["Unable to fetch teams"]

                raise HTTPException(
                    status_code=404,
                    detail=f"Team '{team}' not found. Available teams: {available_teams}",
                )

        # Assign the conversation to the team
        result = await chatwoot.assign_team(conversation_id=conversation_id, team_id=team_id)

        # Log successful result
        logger.info(f"Successfully assigned conversation {conversation_id} to team {team} (ID: {team_id})")

        return {
            "status": "success",
            "conversation_id": conversation_id,
            "team": team,
            "team_id": team_id,
            "result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        # Log the full exception details
        logger.exception(f"Detailed error when assigning team for conversation {conversation_id}:")

        # Get available teams for error details
        try:
            if ENABLE_TEAM_CACHE:
                available_teams = list(team_cache.keys())
            else:
                teams = await chatwoot.get_teams()
                available_teams = [team["name"].lower() for team in teams]
        except Exception:
            available_teams = ["Unable to fetch teams"]

        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "conversation_id": conversation_id,
                "attempted_team": team,
                "available_teams": available_teams,
                "cache_enabled": ENABLE_TEAM_CACHE,
            },
        ) from e


@router.post("/toggle-status/{conversation_id}")
async def toggle_conversation_status(
    conversation_id: int,
    status: ConversationStatus = Body(..., embed=True),
    db: AsyncSession = Depends(get_session),
):
    """
    Toggle the status of a Chatwoot conversation

    Parameters:
    - conversation_id: The ID of the conversation to update (path parameter)
    - status: Status to set (request body)

    Example request body:
        {
            "status": "open"
        }
    """
    try:
        # Get current conversation data to find out the previous status
        previous_status_val: Optional[str] = None
        try:
            conversation_data = await chatwoot.get_conversation_data(conversation_id)
            previous_status_val = conversation_data.get("status")
            logger.info(f"Current status for convo {conversation_id} before toggle: {previous_status_val}")
        except Exception as e_get_status:
            # Log the error but proceed, previous_status will be None
            # The notification logic in toggle_status handles previous_status being None
            logger.warning(f"Could not fetch current status for convo {conversation_id} before toggle: {e_get_status}")

        result = await chatwoot.toggle_status(
            conversation_id=conversation_id,
            status=status.value,
            previous_status=previous_status_val,
            is_error_transition=False,  # This is not an error-induced transition
        )
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "result": result,
        }
    except Exception as e:
        logger.exception(f"Failed to toggle status for conversation {conversation_id}:")
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "conversation_id": conversation_id},
        ) from e


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events manager"""
    # Application startup
    await create_db_tables()
    logger.info("Application startup: Database tables checked/created.")
    # Consider any other startup logic here, e.g., initializing caches, connecting to external services

    if ENABLE_TEAM_CACHE:
        await update_team_cache()
        logger.info(f"Initialized team cache with {len(team_cache)} teams")
    else:
        logger.info("Team caching is disabled. Teams will be fetched directly from API.")

    yield  # Application is now running

    # Application shutdown
    # Consider any cleanup logic here, e.g., closing connections, saving state
    logger.info("Application shutdown: Cleaning up resources.")
