import asyncio
import os

import pytest
from dotenv import load_dotenv
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.chatwoot import ChatwootHandler
from app.config import CHATWOOT_ACCOUNT_ID, CHATWOOT_API_KEY, CHATWOOT_API_URL

# Load environment variables
load_dotenv()


# Create an in-memory database for testing
@pytest.fixture(scope="session")
def test_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture(scope="session")
def create_tables(test_engine):
    SQLModel.metadata.create_all(test_engine)
    yield
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture
def db_session(test_engine, create_tables):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def chatwoot_handler():
    return ChatwootHandler(
        api_url=CHATWOOT_API_URL,
        api_key=CHATWOOT_API_KEY,
        account_id=CHATWOOT_ACCOUNT_ID,
    )


@pytest.fixture
def test_conversation_id():
    # This should be a real test conversation ID in your Chatwoot instance
    return int(os.getenv("TEST_CONVERSATION_ID", "20"))  # Default to 20 as seen in notebook


@pytest.fixture
def wait_for_service():
    """Fixture to wait for a service to be available"""

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
