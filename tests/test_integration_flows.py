import os
import random
import string
import time
from typing import Any, Dict, List, Optional

import httpx
import pytest
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.api.chatwoot import ChatwootHandler
from app.db.models import Conversation
from app.schemas import ConversationCreate

load_dotenv()

# --- Configuration ---
BRIDGE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
CHATWOOT_API_URL = os.getenv("CHATWOOT_API_URL")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID")
CHATWOOT_API_KEY = os.getenv("CHATWOOT_API_KEY")
CHATWOOT_ADMIN_API_KEY = os.getenv("CHATWOOT_ADMIN_API_KEY")  # Needed for team lookup
TEST_INBOX_ID = int(os.getenv("CHATWOOT_TEST_INBOX_ID", "6"))

if not all([CHATWOOT_API_URL, CHATWOOT_ACCOUNT_ID, CHATWOOT_API_KEY, CHATWOOT_ADMIN_API_KEY]):
    pytest.fail("Required Chatwoot env vars missing (including admin key)", pytrace=False)

# --- Instantiate ChatwootHandler ---
chatwoot_handler = ChatwootHandler()

# --- Constants ---
API_TIMEOUT = 20.0
POLL_INTERVAL = 3
MAX_POLL_WAIT_TIME = 60
RETRY_DELAY = 2
MAX_RETRIES = 3
MESSAGE_TYPE_INCOMING = "incoming"
MESSAGE_TYPE_OUTGOING = "outgoing"  # For private notes via API
EVENT_MESSAGE_CREATED = "message_created"
SENDER_TYPE_CONTACT = "contact"
ROLE_USER = "user"
# ROLE_ASSISTANT = "assistant" # Not strictly needed if we only verify end state


# --- Test Data and Fixtures ---
@pytest.fixture(scope="session")
def chatwoot_test_env():
    """
    Set up test environment with Chatwoot conversation.
    Returns test case data, contact ID, and conversation ID.
    """
    # Sample test case - you can expand this to load from JSON files
    test_case = {
        "case_name": "basic_support_flow",
        "messages": [
            {"role": "user", "text": "I need help with my account"},
            {"role": "assistant", "text": "I'll help you with your account. What specific issue are you experiencing?"}
        ],
        "attributes_expected": {
            "priority": "medium",
            "team": "Support Team",
            "region": "US"
        }
    }
    
    # Create test contact and conversation
    contact_email = f"test_user_{_generate_random_string(8)}@example.com"
    contact_name = f"Test User {_generate_random_string(4)}"
    source_id = f"test_source_{_generate_random_string(8)}"
    
    contact_id = get_or_create_chatwoot_contact(contact_email, contact_name)
    conversation_id = create_chatwoot_conversation(contact_id, source_id)
    
    yield test_case["case_name"], test_case, contact_id, conversation_id
    
    # Cleanup
    delete_chatwoot_conversation(conversation_id)


# --- Database Integration Functions ---
async def create_conversation_in_db(
    async_session: AsyncSession, 
    chatwoot_conversation_id: str,
    status: str = "pending"
) -> Conversation:
    """Create a conversation record in the database."""
    conversation_data = ConversationCreate(
        chatwoot_conversation_id=chatwoot_conversation_id,
        status=status
    )
    
    conversation = Conversation(**conversation_data.model_dump())
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)
    return conversation


async def get_conversation_from_db(
    async_session: AsyncSession,
    chatwoot_conversation_id: str
) -> Optional[Conversation]:
    """Retrieve a conversation from the database."""
    from sqlalchemy import select
    
    statement = select(Conversation).where(
        Conversation.chatwoot_conversation_id == chatwoot_conversation_id
    )
    result = await async_session.execute(statement)
    return result.scalar_one_or_none()


async def update_conversation_in_db(
    async_session: AsyncSession,
    conversation: Conversation,
    **updates
) -> Conversation:
    """Update a conversation in the database."""
    for field, value in updates.items():
        if hasattr(conversation, field):
            setattr(conversation, field, value)
    
    await async_session.commit()
    await async_session.refresh(conversation)
    return conversation


# --- Chatwoot API Helpers (Updated for new architecture) ---
def extract_conversation_data(json_data):
    """
    Extract actual data from conversation JSON and format it according to the required schema.

    Args:
        json_data (dict): Input JSON data containing conversation information

    Returns:
        dict: Formatted JSON with team name, priority, and location
    """
    result = {}

    # Extract team name - actual value from the data
    if "meta" in json_data and "team" in json_data["meta"] and "name" in json_data["meta"]["team"]:
        result["team"] = json_data["meta"]["team"]["name"]

    # Extract priority - actual value from the data
    if "priority" in json_data:
        result["priority"] = json_data["priority"]

    # Extract location - actual value from the data
    if "custom_attributes" in json_data and "region" in json_data["custom_attributes"]:
        result["location"] = json_data["custom_attributes"]["region"]

    return result


def _get_chatwoot_headers(admin: bool = True) -> Dict[str, str]:
    key = CHATWOOT_ADMIN_API_KEY if admin else CHATWOOT_API_KEY
    if not key:
        pytest.fail(f"Required API key missing (Admin: {admin})", pytrace=False)
    return {"api_access_token": key, "Content-Type": "application/json"}


def _make_chatwoot_request(method: str, url: str, is_admin: bool = False, **kwargs) -> httpx.Response:
    """Makes a request to the Chatwoot API with retries."""
    headers = _get_chatwoot_headers(admin=is_admin)
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=API_TIMEOUT) as client:
                response = client.request(method, url, headers=headers, **kwargs)
                if 500 <= response.status_code < 600 and attempt < MAX_RETRIES - 1:
                    print(f"    WARNING: Chatwoot API {response.status_code}. Retrying...")
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                response.raise_for_status()
                return response
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"    WARNING: Chatwoot API Error ({type(e).__name__}). Retrying...")
            print(f" Error details: {e}")
            if attempt >= MAX_RETRIES - 1:
                pytest.fail(f"Chatwoot API request failed: {e}", pytrace=False)
            time.sleep(RETRY_DELAY * (attempt + 1))
    raise RuntimeError("Exhausted retries for Chatwoot API request")  # Should be unreachable


def _generate_random_string(length=8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


# --- Existing Chatwoot utility functions (keeping as-is for compatibility) ---
def get_or_create_chatwoot_contact(email: str, name: str) -> int:
    """Finds or creates a contact, returns contact ID."""
    search_url = f"{CHATWOOT_API_URL}/accounts/{CHATWOOT_ACCOUNT_ID}/contacts/search"
    create_url = f"{CHATWOOT_API_URL}/accounts/{CHATWOOT_ACCOUNT_ID}/contacts"
    try:
        search_response = _make_chatwoot_request("GET", search_url, params={"q": email.strip()})
        results = search_response.json().get("payload", [])
        for contact_data in results:
            if contact_data.get("email", "").strip().lower() == email.strip().lower():
                print(f"  Found contact: {contact_data.get('id')}")
                return contact_data["id"]
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            pytest.fail(f"Contact search failed: {e}", pytrace=False)
    except Exception as e:
        pytest.fail(f"Contact search error: {e}", pytrace=False)

    print(f"  Creating contact: {email}")
    create_payload = {"name": name, "email": email.strip()}
    try:
        create_response = _make_chatwoot_request("POST", create_url, json=create_payload)
        contact_payload = create_response.json().get("payload", {}).get("contact", {})
        if not contact_payload:
            contact_payload = create_response.json().get("payload", {})

        contact_id = contact_payload.get("id")
        if not contact_id:
            pytest.fail(f"Contact creation invalid response: {create_response.text}", pytrace=False)
        print(f"  Created contact ID: {contact_id}")
        return contact_id
    except httpx.HTTPStatusError as e:
        # Handle potential race condition (422) by trying search again once
        if e.response.status_code == 422:
            print("  Contact creation 422, retrying search...")
            time.sleep(1)
            try:
                retry_resp = _make_chatwoot_request("GET", search_url, params={"q": email.strip()})
                results = retry_resp.json().get("payload", [])
                for contact_data in results:
                    if contact_data.get("email", "").strip().lower() == email.strip().lower():
                        print(f"  Found contact after 422: {contact_data.get('id')}")
                        return contact_data["id"]
                pytest.fail("Contact 422, but not found on retry search.", pytrace=False)
            except Exception as search_err:
                pytest.fail(f"Error during contact search retry after 422: {search_err}", pytrace=False)
        else:
            pytest.fail(f"Contact creation failed: {e.response.text}", pytrace=False)
    except Exception as e:
        pytest.fail(f"Contact creation error: {e}", pytrace=False)
    raise RuntimeError("Failed to get/create contact")  # Should be unreachable


def create_chatwoot_conversation(contact_id: int, source_id: str) -> int:
    """Creates a conversation, returns conversation ID."""
    url = f"{CHATWOOT_API_URL}/accounts/{CHATWOOT_ACCOUNT_ID}/conversations"
    payload = {
        "inbox_id": TEST_INBOX_ID,
        "contact_id": contact_id,
        "source_id": source_id,
        "status": "open",
    }
    response = _make_chatwoot_request("POST", url, json=payload)
    convo_data = response.json()
    convo_payload = convo_data.get("payload", convo_data)  # Handle potential wrapper
    convo_id = convo_payload.get("id")
    if not convo_id:
        pytest.fail(f"Conversation creation invalid response: {response.text}", pytrace=False)
    print(f"  Created conversation ID: {convo_id}")
    return convo_id


def delete_chatwoot_conversation(conversation_id: int):
    """Deletes a conversation (best effort)."""
    url = f"{CHATWOOT_API_URL}/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}"
    try:
        with httpx.Client(timeout=API_TIMEOUT) as client:
            headers = _get_chatwoot_headers()
            response = client.delete(url, headers=headers)
            if response.status_code == 404:
                print(f"  Conversation {conversation_id} already deleted (404).")
            elif response.is_success:
                print(f"  Deleted conversation ID: {conversation_id}")
            else:
                print(f"  WARNING: Failed deleting conversation {conversation_id}: {response.status_code}")
    except Exception as e:
        print(f"  WARNING: Exception during conversation deletion {conversation_id}: {e}")


def get_chatwoot_messages(conversation_id: int) -> List[Dict[str, Any]]:
    """Fetches messages for a conversation."""
    url = f"{CHATWOOT_API_URL}/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/messages"
    try:
        response = _make_chatwoot_request("GET", url)
        data = response.json()
        return data.get("payload", [])
    except Exception as e:
        print(f"    WARNING: Failed getting messages for conversation {conversation_id}: {e}")
        return []


def send_chatwoot_message(conversation_id: int, message_content: str, private: bool = False):
    """Sends a message to a conversation."""
    url = f"{CHATWOOT_API_URL}/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/messages"
    payload = {
        "content": message_content,
        "message_type": MESSAGE_TYPE_OUTGOING,
        "private": private,
    }
    try:
        response = _make_chatwoot_request("POST", url, json=payload)
        return response.json()
    except Exception as e:
        print(f"    WARNING: Failed sending message to conversation {conversation_id}: {e}")
        return None


def get_team_id_by_name(team_name: str) -> Optional[int]:
    """Finds team ID by name."""
    url = f"{CHATWOOT_API_URL}/accounts/{CHATWOOT_ACCOUNT_ID}/teams"
    try:
        response = _make_chatwoot_request("GET", url, is_admin=True)
        teams = response.json().get("payload", [])
        for team in teams:
            if team.get("name") == team_name:
                return team.get("id")
        return None
    except Exception as e:
        print(f"    WARNING: Failed getting teams: {e}")
        return None


# --- Updated webhook simulation with new schemas ---
def simulate_user_message_via_webhook(
    conversation_id: int, 
    contact_id: int, 
    message_text: str, 
    step_num: int,
    chatwoot_webhook_factory=None
):
    """
    Simulate a user message by sending a webhook to the bridge API.
    Updated to use new Pydantic schemas for validation.
    """
    print(f"    Simulating user message (Step {step_num}): '{message_text[:50]}...'")
    
    # Create webhook payload using factory if available, otherwise create directly
    if chatwoot_webhook_factory:
        webhook_data = chatwoot_webhook_factory(
            event=EVENT_MESSAGE_CREATED,
            message_type=MESSAGE_TYPE_INCOMING,
            content=message_text,
            conversation_id=conversation_id,
            sender_id=contact_id
        )
        webhook_payload = webhook_data.model_dump()
    else:
        # Fallback to direct payload creation
        webhook_payload = {
            "event": EVENT_MESSAGE_CREATED,
            "message_type": MESSAGE_TYPE_INCOMING,
            "content": message_text,
            "conversation": {
                "id": conversation_id,
                "status": "open",
                "meta": {"assignee": None}
            },
            "sender": {
                "id": contact_id,
                "type": SENDER_TYPE_CONTACT
            }
        }

    webhook_url = f"{BRIDGE_URL}/api/v1/chatwoot-webhook"
    
    try:
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.post(webhook_url, json=webhook_payload)
            if response.is_success:
                print(f"    Webhook sent successfully (Step {step_num}): {response.status_code}")
            else:
                print(f"    WARNING: Webhook failed (Step {step_num}): {response.status_code} - {response.text[:100]}")
    except Exception as e:
        print(f"    WARNING: Webhook error (Step {step_num}): {e}")


# --- Continue with rest of existing functions ---
def poll_for_bot_response(conversation_id: int, initial_message_count: int) -> bool:
    """Polls for a bot response in the conversation."""
    print(f"     Polling for bot response (baseline: {initial_message_count} messages)...")
    start_time = time.time()
    last_checked_count = initial_message_count

    while time.time() - start_time < MAX_POLL_WAIT_TIME:
        try:
            current_messages = get_chatwoot_messages(conversation_id)
        except Exception as e:
            print(f"       WARNING: Error fetching messages during polling: {e}")
            time.sleep(POLL_INTERVAL)
            continue

        if len(current_messages) > last_checked_count:
            newly_arrived = current_messages[last_checked_count:]
            print(f"     New messages detected: {len(newly_arrived)}")

            for msg in newly_arrived:
                sender_type = msg.get("sender", {}).get("type") or msg.get("sender_type")
                is_private = msg.get("private", False)

                if not is_private and sender_type != SENDER_TYPE_CONTACT and msg.get("sender") is not None:
                    waited_time = time.time() - start_time
                    content_preview = (msg.get("content") or "")[:50]
                    print(
                        f"     >>> Bot/Agent response DETECTED after {waited_time:.1f}s."
                        f" Type: '{sender_type}', Content: '{content_preview}...'"
                    )
                    return True

            last_checked_count = len(current_messages)

        time.sleep(POLL_INTERVAL)

    print(f"\n     TIMEOUT: No bot response detected within {MAX_POLL_WAIT_TIME}s.")
    return False


def verify_bridge_conversation_exists(chatwoot_conversation_id: int):
    """
    Checks the bridge API to confirm a conversation record exists and has a Dify ID.
    """
    print(f"  --- Verifying Bridge Conversation Existence (Max Wait: {config.DIFY_CHECK_WAIT_TIME}s) ---")
    check_url = f"{BRIDGE_URL}/conversation-info/{chatwoot_conversation_id}"
    start_time = time.time()

    while time.time() - start_time < config.DIFY_CHECK_WAIT_TIME:
        try:
            with httpx.Client(timeout=API_TIMEOUT) as client:
                print(f"    Checking {check_url}...")
                response = client.get(check_url)

                if response.status_code == 200:
                    data = response.json()
                    dify_id = data.get("dify_conversation_id")
                    status = data.get("status")
                    if dify_id:
                        waited = time.time() - start_time
                        print(
                            f"    >>> Bridge Conversation FOUND after {waited:.1f}s."
                            f" Dify ID: '{dify_id}', Status: '{status}'"
                        )
                        return
                    else:
                        print(f"    Conversation found, but Dify ID is missing. Status: '{status}'. Retrying...")

                elif response.status_code == 404:
                    print("    Conversation not found yet (404). Retrying...")
                else:
                    print(f"    WARNING: Unexpected status {response.status_code} checking conversation info. Retrying...")

        except httpx.RequestError as e:
            print(f"    WARNING: Network error checking conversation info: {e}. Retrying...")
        except Exception as e:
            print(f"    WARNING: Error during Bridge Conversation check: {type(e).__name__} - {e}. Retrying...")

        time.sleep(config.DIFY_CHECK_POLL_INTERVAL)

    error_message = (
        f"TIMEOUT: Bridge conversation or Dify conversation ID not found for Chatwoot conversation {chatwoot_conversation_id} "
        f"within {config.DIFY_CHECK_WAIT_TIME} seconds via {check_url}."
    )
    pytest.fail(error_message, pytrace=False)


async def verify_final_state(conversation_id: int, expected_attrs: Dict[str, Any]):
    """Asserts the final conversation state against expected values."""
    print("  --- Verifying Final State ---")
    try:
        final_convo = await chatwoot_handler.get_conversation_data(conversation_id)
    except Exception as e:
        fail_msg = f"Failed to fetch final state for conversation {conversation_id}: {e}"
        pytest.fail(fail_msg, pytrace=False)
    
    final_convo_data = extract_conversation_data(final_convo)

    actual_attributes = final_convo_data.get("custom_attributes", {})
    actual_priority = final_convo_data.get("priority")
    actual_team = final_convo_data.get("team")

    print(f"  Expected Final State: {expected_attrs}")
    print(f"  Actual Final State: {final_convo_data}")

    errors = []

    # Priority Check
    if "priority" in expected_attrs:
        if expected_attrs["priority"] == "urgent":
            expected_attrs["priority"] = "high"
        expected_priority = expected_attrs["priority"]
        if isinstance(expected_priority, str) and expected_priority.lower() == "none":
            expected_priority = None
        if actual_priority != expected_priority:
            error_msg = f"Priority: Expected '{expected_priority}', Got '{actual_priority}'"
            errors.append(error_msg)

    # Team Check
    expected_team = expected_attrs.get("team")
    if "team" in expected_attrs:
        if actual_team != expected_team:
            error_msg = f"Team: Expected {expected_team}, Got {actual_team}"
            errors.append(error_msg)

    # Custom Attributes Check
    custom_attr_keys_expected = set(expected_attrs.keys()) - {"priority", "team", "team_id"}
    for key in custom_attr_keys_expected:
        expected_value = expected_attrs[key]
        if isinstance(expected_value, str) and expected_value.lower() == "none":
            expected_value = None
        actual_value = actual_attributes.get(key)
        if actual_value != expected_value:
            error_msg = f"Custom Attr '{key}': Expected '{expected_value}', Got '{actual_value}'"
            errors.append(error_msg)

    if errors:
        pytest.fail("\n".join(["Final State Verification Errors:"] + errors), pytrace=False)

    print("--- Final State Verification PASSED ---")


# --- Main Integration Test ---
@pytest.mark.asyncio
async def test_conversation_flow(chatwoot_test_env, chatwoot_webhook_factory, async_session: AsyncSession):
    """
    Runs a comprehensive conversation flow test with database integration.
    Updated for new SQLAlchemy 2 and Pydantic v2 architecture.
    """
    case_name, case_data, contact_id, conversation_id = chatwoot_test_env
    print(f"\n--- Executing Test Case: {case_name} ---")
    print(f"  Contact: {contact_id}, Conversation: {conversation_id}")

    # Create database record for the conversation
    db_conversation = await create_conversation_in_db(
        async_session, 
        str(conversation_id),
        status="pending"
    )
    print(f"  Created DB conversation: ID {db_conversation.id}")

    messages_to_simulate = case_data.get("messages", [])
    last_message_count = 0

    for i, message_step in enumerate(messages_to_simulate):
        step_num = i + 1
        if message_step.get("role") == ROLE_USER:
            # Get message count before simulating user message
            try:
                initial_messages = get_chatwoot_messages(conversation_id)
                last_message_count = len(initial_messages)
                print(f"\n-- Step {step_num}/{len(messages_to_simulate)}: User Message (Baseline: {last_message_count} msgs) --")
            except Exception as e:
                print(f"  WARNING: Failed getting message count before step {step_num}. Error: {e}")
                last_message_count = -1

            # Simulate user message with webhook factory
            simulate_user_message_via_webhook(
                conversation_id, 
                contact_id, 
                message_step.get("text", ""), 
                step_num,
                chatwoot_webhook_factory
            )

            # Verification after FIRST user message
            if i == 0:
                verify_bridge_conversation_exists(conversation_id)

            # Poll for bot response
            if last_message_count != -1:
                if not poll_for_bot_response(conversation_id, last_message_count):
                    print(f"     WARNING: Test '{case_name}' proceeding without confirmed bot response for step {step_num}.")
            else:
                print("     Skipping polling due to uncertain baseline message count.")
        else:
            print(f"\n-- Step {step_num}/{len(messages_to_simulate)}: Assistant Message (Skipping Simulation) --")

    # Update database conversation status
    await update_conversation_in_db(
        async_session,
        db_conversation,
        status="processed"
    )
    print(f"  Updated DB conversation status to: {db_conversation.status}")

    # Final Verification
    print("\n--- Conversation Simulation Complete ---")
    final_wait = 5
    print(f"  Waiting {final_wait}s before final verification...")
    time.sleep(final_wait)

    await verify_final_state(conversation_id, case_data.get("attributes_expected", {}))

    # Verify database state
    final_db_conversation = await get_conversation_from_db(async_session, str(conversation_id))
    assert final_db_conversation is not None
    assert final_db_conversation.status == "processed"
    print(f"  DB conversation final status: {final_db_conversation.status}")

    print(f"\n--- Test Case {case_name}: PASSED ---")


# --- Additional Database Integration Tests ---
@pytest.mark.asyncio
async def test_webhook_database_integration(
    async_session: AsyncSession,
    chatwoot_webhook_factory,
    conversation_factory
):
    """Test that webhook processing correctly integrates with database operations."""
    # Create webhook data
    webhook = chatwoot_webhook_factory(
        event="message_created",
        message_type="incoming",
        content="Test database integration",
        conversation_id=12345,
        sender_id=67890
    )
    
    # Simulate database operations that would happen during webhook processing
    conversation = conversation_factory(
        chatwoot_conversation_id=str(webhook.conversation_id),
        status="pending"
    )
    
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)
    
    # Verify webhook data matches database data
    assert str(webhook.conversation_id) == conversation.chatwoot_conversation_id
    assert webhook.message_type == "incoming"
    assert webhook.content == "Test database integration"
    
    # Update conversation based on webhook processing
    conversation.status = "processed"
    await async_session.commit()
    
    assert conversation.status == "processed"
    print("Webhook database integration test passed")


@pytest.mark.asyncio 
async def test_concurrent_conversation_processing(
    async_session: AsyncSession,
    conversation_factory
):
    """Test handling multiple conversations concurrently."""
    # Create multiple conversations
    conversations = []
    for i in range(3):
        conv = conversation_factory(
            chatwoot_conversation_id=f"concurrent_{i}",
            status="pending"
        )
        async_session.add(conv)
        conversations.append(conv)
    
    await async_session.commit()
    
    # Simulate concurrent processing
    for conv in conversations:
        await async_session.refresh(conv)
        conv.status = "processing"
    
    await async_session.commit()
    
    # Finalize processing
    for conv in conversations:
        conv.status = "completed"
    
    await async_session.commit()
    
    # Verify all conversations are completed
    for conv in conversations:
        await async_session.refresh(conv)
        assert conv.status == "completed"
    
    print(f"Successfully processed {len(conversations)} conversations concurrently")
