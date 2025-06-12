import json
import os
import random
import string
import time
from typing import Any, Dict, Generator, List, Optional, Tuple

import httpx
import pytest
from dotenv import load_dotenv

from app import config
from app.api.chatwoot import ChatwootHandler

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


# --- Minimal Chatwoot API Helpers ---
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
        print(f"  WARNING: Failed to get messages for convo {conversation_id}: {e}")
        return []  # Return empty on error to allow polling logic to continue


def send_chatwoot_message(conversation_id: int, message_content: str, private: bool = False):
    """Sends a message via API (used for private notes)."""
    url = f"{CHATWOOT_API_URL}/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/messages"
    payload = {
        "content": message_content,
        "message_type": MESSAGE_TYPE_OUTGOING,  # API sends notes as 'outgoing'
        "private": private,
    }
    print(f"    -> Sending Chatwoot {'PRIVATE NOTE' if private else 'MESSAGE (rare?)'}: '{message_content[:50]}...'")
    try:
        _make_chatwoot_request("POST", url, json=payload)
        print("    Message sent via API successfully.")
    except Exception as e:
        # Only warn for private notes, fail otherwise (though we primarily use this for private notes)
        log_func = print if private else pytest.fail
        log_func(f"    {'WARNING:' if private else 'FAILURE:'} Failed to send API message: {e}")


# --- Team Cache Helper ---
_team_name_to_id_cache: Optional[Dict[str, int]] = None


def get_team_id_by_name(team_name: str) -> Optional[int]:
    """Gets team ID by name, using cached teams (requires Admin key)."""
    global _team_name_to_id_cache
    if _team_name_to_id_cache is None:
        print("    Fetching and caching teams...")
        teams_url = f"{CHATWOOT_API_URL}/accounts/{CHATWOOT_ACCOUNT_ID}/teams"
        try:
            # Requires Admin key
            response = _make_chatwoot_request("GET", teams_url, is_admin=True)
            teams_data = response.json()
            teams_list = teams_data
            if not isinstance(teams_list, list):
                pytest.fail(f"Unexpected teams format: {teams_list}", pytrace=False)
            _team_name_to_id_cache = {
                team["name"].lower(): team["id"]
                for team in teams_list
                if isinstance(team, dict) and "name" in team and "id" in team
            }
            print(f"    Cached {len(_team_name_to_id_cache)} teams.")
        except Exception as e:
            pytest.fail(f"Failed to fetch or cache teams: {e}", pytrace=False)

    # Defensive check
    if _team_name_to_id_cache is None:
        pytest.fail("Team cache failed to initialize.", pytrace=False)

    return _team_name_to_id_cache.get(team_name.lower())


# # --- Test Data Loading ---
# try:
#     with open("data/minimal_test_flows.json", "r", encoding="utf-8") as f:
#         test_cases: Dict[str, Dict[str, Any]] = json.load(f)
# except Exception as e:
#     pytest.fail(f"Failed to load test data: data/minimal_test_flows.json. Error: {e}", pytrace=False)


# --- Test Fixture ---
# @pytest.fixture(scope="function", params=test_cases.items(), ids=list(test_cases.keys()))
# def chatwoot_test_env(request) -> Generator[Tuple[str, Dict, int, int], None, None]:
#     """Sets up Chatwoot contact and conversation, yields IDs, cleans up."""
#     case_name, case_data = request.param
#     print(f"\n--- Setup: {case_name} ---")
#     contact_email = f"test_{case_name.replace(' ', '_').lower()}@example.com"
#     contact_name = f"Test {case_name}"
#     source_id = f"test-src-{case_name.replace(' ', '_').lower()}-{_generate_random_string(6)}"

#     contact_id = None
#     conversation_id = None
#     try:
#         contact_id = get_or_create_chatwoot_contact(email=contact_email, name=contact_name)
#         conversation_id = create_chatwoot_conversation(contact_id=contact_id, source_id=source_id)
#         print(f"  Fixture Setup Complete. Contact: {contact_id}, Conversation: {conversation_id}")
#         yield case_name, case_data, contact_id, conversation_id  # Yield basic info

#     finally:
#         print(f"\n--- Teardown: {case_name} ---")
#         if conversation_id:
#             # delete_chatwoot_conversation(conversation_id) # Keep deletion commented for debugging
#             print(f"  Skipping conversation deletion for {conversation_id}")
#         else:
#             print("  No conversation created, skipping deletion.")
#         # Optional: Delete contact? Usually not needed for tests.


# --- Core Test Logic ---


def simulate_user_message_via_webhook(conversation_id: int, contact_id: int, message_text: str, step_num: int):
    """Sends private note hack + minimal webhook POST to bridge."""
    print(f"  -> Simulating User Message (Step {step_num}): '{message_text[:100]}...'")

    # 1. Send Private Note Hack
    private_note_content = f"[Test Step {step_num}] User sends: {message_text}..."
    send_chatwoot_message(conversation_id, private_note_content, private=True)
    time.sleep(0.5)  # Small delay

    # 2. Send Minimal Webhook to Bridge
    webhook_url = f"{BRIDGE_URL}/chatwoot-webhook"
    # Construct a *minimal* payload expected by the bridge for a message_created event
    payload = {
        "event": EVENT_MESSAGE_CREATED,
        "message_type": MESSAGE_TYPE_INCOMING,
        "private": False,
        "content": message_text,
        "conversation": {"id": conversation_id},
        "sender": {"id": contact_id, "type": SENDER_TYPE_CONTACT},  # Assume bridge needs sender ID and type
        "account": {"id": int(CHATWOOT_ACCOUNT_ID) if CHATWOOT_ACCOUNT_ID else None},
        "inbox": {"id": TEST_INBOX_ID},
        # Add sender_type = SENDER_TYPE_CONTACT if bridge expects it top-level
        "sender_type": SENDER_TYPE_CONTACT,
    }
    # Remove None values if necessary, depending on bridge handler strictness
    payload = {k: v for k, v in payload.items() if v is not None}

    print(f"     POST {webhook_url}")
    try:
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.post(webhook_url, json=payload)
            print(f"     Bridge Response: {response.status_code}")
            # print(f"     Bridge Body: {response.text[:200]}...") # Uncomment for debug
            response.raise_for_status()  # Fail test if bridge gives error
        time.sleep(1)  # Allow bridge processing time
    except Exception as e:
        pytest.fail(f"Webhook request failed: {e}", pytrace=False)


def poll_for_bot_response(conversation_id: int, initial_message_count: int) -> bool:
    """Polls Chatwoot for new non-private messages not sent by the contact."""
    print(f"     Polling for bot response (Max {MAX_POLL_WAIT_TIME}s)... Baseline: {initial_message_count} msgs")
    start_time = time.time()
    last_checked_count = initial_message_count

    while time.time() - start_time < MAX_POLL_WAIT_TIME:
        time.sleep(POLL_INTERVAL)
        current_messages = get_chatwoot_messages(conversation_id)
        # Handle case where initial fetch failed or returns empty list unexpectedly
        if not current_messages and last_checked_count <= 0:
            # If baseline was 0 or failed (-1), and current is empty, keep polling
            if last_checked_count == -1:
                print("     Polling: Waiting for initial messages to appear or baseline fetch to succeed...")
            continue  # Keep polling if we couldn't establish baseline or no messages yet

        if len(current_messages) > last_checked_count or last_checked_count == -1:
            # If baseline was uncertain (-1), check all messages
            start_index = last_checked_count if last_checked_count != -1 else 0
            newly_arrived = current_messages[start_index:]

            for msg in newly_arrived:
                sender_type = msg.get("sender", {}).get("type") or msg.get("sender_type")
                is_private = msg.get("private", False)

                # Found a non-private message not from the original contact? Assume it's the bot/agent.
                # Also check sender is not None to avoid matching system messages without senders
                if not is_private and sender_type != SENDER_TYPE_CONTACT and msg.get("sender") is not None:
                    waited_time = time.time() - start_time
                    content_preview = (msg.get("content") or "")[:50]
                    print(
                        f"     >>> Bot/Agent response DETECTED after {waited_time:.1f}s."
                        f" Type: '{sender_type}', Content: '{content_preview}...'"
                    )
                    return True  # Bot response detected

            # Update count if new messages arrived but were not the target bot response
            last_checked_count = len(current_messages)
        # else: # Print dots only if no new messages at all
        # print(".", end="", flush=True) # Optional: progress indicator

    print(f"\n     TIMEOUT: No bot response detected within {MAX_POLL_WAIT_TIME}s.")
    return False


def verify_bridge_dialogue_exists(chatwoot_conversation_id: int):
    """
    Checks the bridge API to confirm a dialogue record exists and has a Dify ID.
    Logs the status found in the dialogue record.
    """
    print(f"  --- Verifying Bridge Dialogue Existence (Max Wait: {config.DIFY_CHECK_WAIT_TIME}s) ---")
    check_url = f"{BRIDGE_URL}/dialogue-info/{chatwoot_conversation_id}"
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
                            f"    >>> Bridge Dialogue FOUND after {waited:.1f}s."
                            f" Dify ID: '{dify_id}', Status: '{status}'"
                        )
                        return  # Success!
                    else:
                        print(f"    Dialogue found, but Dify ID is missing. Status: '{status}'. Retrying...")

                elif response.status_code == 404:
                    print("    Dialogue not found yet (404). Retrying...")
                else:
                    # Log unexpected errors but continue polling
                    print(f"    WARNING: Unexpected status {response.status_code} checking dialogue info. Retrying...")
                    print(f"    Response: {response.text[:200]}...")

        except httpx.RequestError as e:
            print(f"    WARNING: Network error checking dialogue info: {e}. Retrying...")
        except Exception as e:
            # Catch broader errors during check
            print(f"    WARNING: Error during Bridge Dialogue check: {type(e).__name__} - {e}. Retrying...")

        time.sleep(config.DIFY_CHECK_POLL_INTERVAL)

    # If loop finishes without returning, it timed out
    error_message = (
        f"TIMEOUT: Bridge dia or Dify conversation ID not found for Chatwoot conversation {chatwoot_conversation_id} "
        f"within {config.DIFY_CHECK_WAIT_TIME} seconds via {check_url}."
    )
    pytest.fail(error_message, pytrace=False)


async def verify_final_state(conversation_id: int, expected_attrs: Dict[str, Any]):
    """Asserts the final conversation state against expected values."""
    print("  --- Verifying Final State ---")
    try:
        # Use the async ChatwootHandler method
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
            expected_attrs["priority"] = "high"  # Договорились, что urgent ставят люди
        expected_priority = expected_attrs["priority"]
        # Allow "none" string to mean None/null
        if isinstance(expected_priority, str) and expected_priority.lower() == "none":
            expected_priority = None
        if actual_priority != expected_priority:
            error_msg = f"Priority: Expected '{expected_priority}', Got '{actual_priority}'"
            errors.append(error_msg)

    # Team Check (Handle lookup by name)
    expected_team = expected_attrs.get("team")

    if "team" in expected_attrs:
        if actual_team != expected_team:
            error_msg = f"Team ID: Expected {expected_team}, Got {actual_team}"
            errors.append(error_msg)

    # Custom Attributes Check
    custom_attr_keys_expected = set(expected_attrs.keys()) - {"priority", "team", "team_id"}
    for key in custom_attr_keys_expected:
        expected_value = expected_attrs[key]
        if isinstance(expected_value, str) and expected_value.lower() == "none":
            expected_value = None  # Allow "none" string to mean null/None
        actual_value = actual_attributes.get(key)
        if actual_value != expected_value:
            error_msg = f"Custom Attr '{key}': Expected '{expected_value}', Got '{actual_value}'"
            errors.append(error_msg)

    # Check for unexpected custom attributes that were not in the expectation list
    # for key in actual_attributes:
    #     if key not in custom_attr_keys_expected:
    #          errors.append(f"Unexpected Custom Attr '{key}' found with value: '{actual_attributes[key]}'")

    if errors:
        pytest.fail("\n".join(["Final State Verification Errors:"] + errors), pytrace=False)

    print("--- Final State Verification PASSED ---")


# --- The Test ---
@pytest.mark.asyncio
async def test_conversation_flow(chatwoot_test_env):
    """Runs a single test case flow."""
    case_name, case_data, contact_id, conversation_id = chatwoot_test_env
    print(f"\n--- Executing Test Case: {case_name} ---")
    print(f"  Contact: {contact_id}, Conversation: {conversation_id}")

    messages_to_simulate = case_data.get("messages", [])
    last_message_count = 0

    for i, message_step in enumerate(messages_to_simulate):
        step_num = i + 1
        if message_step.get("role") == ROLE_USER:
            # Get message count *before* simulating user message
            try:
                # Get fresh count before sending
                initial_messages = get_chatwoot_messages(conversation_id)
                last_message_count = len(initial_messages)
                print(
                    f"\n-- Step {step_num}/{len(messages_to_simulate)}: User Message (Baseline: {last_message_count} msgs) --"  # noqa E501
                )
            except Exception as e:
                print(
                    f"  WARNING: Failed getting message count before step {step_num}. Polling may be inaccurate. Error: {e}"  # noqa E501
                )
                last_message_count = -1  # Indicate baseline uncertainty

            simulate_user_message_via_webhook(conversation_id, contact_id, message_step.get("text", ""), step_num)

            # --- Verification after FIRST user message ---
            if i == 0:
                verify_bridge_dialogue_exists(conversation_id)  # Use the renamed function
            # --- End verification ---

            # Poll for bot response if baseline count is reliable
            if last_message_count != -1:
                if not poll_for_bot_response(conversation_id, last_message_count):
                    # Decide if timeout is fatal. For now, just warn.
                    print(
                        f"     WARNING: Test '{case_name}' proceeding without confirmed bot response for step {step_num}."  # noqa E501
                    )
                    # pytest.fail(f"Timeout waiting for bot response after step {step_num}", pytrace=False)
            else:
                print("     Skipping polling due to uncertain baseline message count.")
                # Optional: Add a small fixed sleep if skipping polling entirely seems too fast
                # time.sleep(POLL_INTERVAL)
        else:
            # Skip assistant message definitions in the JSON for now
            print(f"\n-- Step {step_num}/{len(messages_to_simulate)}: Assistant Message (Skipping Simulation) --")
            pass

    # --- Final Verification ---
    print("\n--- Conversation Simulation Complete ---")
    final_wait = 5
    print(f"  Waiting {final_wait}s before final verification...")
    time.sleep(final_wait)

    await verify_final_state(conversation_id, case_data.get("attributes_expected", {}))

    print(f"\n--- Test Case {case_name}: PASSED ---")
