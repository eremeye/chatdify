# Test Suite Documentation

## Overview

This test suite has been updated to work with the new SQLAlchemy 2 and Pydantic v2 architecture. It provides comprehensive testing coverage for API endpoints, database operations, Chatwoot integrations, and end-to-end workflows.

## Architecture

### Test Structure

```
tests/
├── conftest.py              # Test fixtures and configuration
├── test_api_endpoints.py    # API endpoint testing
├── test_chatwoot_integration.py  # Chatwoot service integration tests  
├── test_integration_flows.py     # End-to-end workflow tests
├── test_utils.py            # Test utilities and helpers
├── README.md               # This documentation
└── pytest.ini             # Pytest configuration
```

### Key Components

#### 1. **Modern Async Testing** (`conftest.py`)
- **Async Session Management**: Uses SQLAlchemy 2 async sessions with proper transaction isolation
- **Test Database**: In-memory SQLite with automatic setup/teardown
- **Factory Patterns**: Pydantic v2 schema factories for consistent test data
- **Mock Integration**: AsyncMock handlers for external service testing

#### 2. **API Testing** (`test_api_endpoints.py`)  
- **Dependency Injection**: FastAPI dependency overrides for database sessions
- **Schema Validation**: Pydantic v2 request/response validation testing
- **Error Handling**: Comprehensive validation error and timeout testing
- **Mock Integration**: External service mocking for isolated testing

#### 3. **Integration Testing** (`test_chatwoot_integration.py`)
- **Real & Mock Testing**: Both live Chatwoot API and mocked service testing
- **Database Integration**: Database operations combined with external API calls
- **Webhook Validation**: Pydantic v2 webhook schema testing
- **Bulk Operations**: Concurrent conversation processing tests

#### 4. **End-to-End Testing** (`test_integration_flows.py`)
- **Complete Workflows**: Full conversation flows from webhook to completion
- **Database Persistence**: Database state verification throughout workflows  
- **External Service Integration**: Real Chatwoot API integration testing
- **State Verification**: Final state validation against expected outcomes

## Usage

### Running Tests

```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m asyncio       # Async tests only

# Run specific test files
pytest tests/test_api_endpoints.py
pytest tests/test_chatwoot_integration.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=app tests/
```

### Environment Setup

#### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost/test_chatdify

# Chatwoot Integration (for integration tests)
CHATWOOT_API_URL=https://your-chatwoot.domain.com/api/v1
CHATWOOT_ACCOUNT_ID=1
CHATWOOT_API_KEY=your_api_key
CHATWOOT_ADMIN_API_KEY=your_admin_key
CHATWOOT_TEST_INBOX_ID=6
TEST_CONVERSATION_ID=20

# API
API_BASE_URL=http://localhost:8000/api/v1
```

#### Docker Setup (Recommended)

```bash
# Start test services
docker-compose -f docker-compose.test.yml up -d

# Run tests in container
docker-compose -f docker-compose.test.yml exec web pytest

# Cleanup
docker-compose -f docker-compose.test.yml down
```

## Test Patterns

### 1. Database Testing with Async Sessions

```python
async def test_conversation_creation(async_session: AsyncSession, conversation_factory):
    """Test creating conversations in database."""
    # Create conversation using factory
    conversation = conversation_factory(
        chatwoot_conversation_id="test_123",
        status="pending"
    )
    
    # Add to database
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)
    
    # Verify creation
    assert conversation.id is not None
    assert conversation.status == "pending"
```

### 2. API Testing with Dependency Overrides

```python
async def test_api_endpoint(test_client, async_session):
    """Test API endpoints with database integration."""
    # Test client automatically uses overridden database session
    response = test_client.post("/conversations", json={
        "chatwoot_conversation_id": "api_test_123",
        "status": "pending"
    })
    
    assert response.status_code == 200
    data = response.json()
    
    # Validate response schema
    conversation_response = ConversationResponse.model_validate(data)
    assert conversation_response.chatwoot_conversation_id == "api_test_123"
```

### 3. Mock Testing for External Services

```python
async def test_chatwoot_integration_mocked(mock_chatwoot_handler):
    """Test Chatwoot integration with mocks."""
    # Mock handler provides predefined responses
    teams = await mock_chatwoot_handler.get_teams()
    assert len(teams) > 0
    assert teams[0]["name"] == "Test Team"
    
    # Verify mock was called
    mock_chatwoot_handler.get_teams.assert_called_once()
```

### 4. Webhook Testing with Pydantic v2

```python
async def test_webhook_processing(chatwoot_webhook_factory):
    """Test webhook payload validation and processing."""
    # Create webhook using factory
    webhook = chatwoot_webhook_factory(
        event="message_created",
        message_type="incoming",
        content="Test message",
        conversation_id=123
    )
    
    # Validate schema
    assert webhook.event == "message_created"
    assert webhook.conversation_id == 123
    
    # Test computed fields
    assert webhook.sender_id is not None
```

### 5. Integration Flow Testing

```python
async def test_end_to_end_flow(
    chatwoot_test_env, 
    async_session: AsyncSession,
    chatwoot_webhook_factory
):
    """Test complete conversation flow."""
    case_name, case_data, contact_id, conversation_id = chatwoot_test_env
    
    # Create database record
    db_conversation = await create_conversation_in_db(
        async_session, str(conversation_id)
    )
    
    # Simulate webhook processing
    webhook = chatwoot_webhook_factory(conversation_id=conversation_id)
    # ... process webhook ...
    
    # Verify final state
    final_conversation = await get_conversation_from_db(
        async_session, str(conversation_id)
    )
    assert final_conversation.status == "processed"
```

## Test Data Management

### Factories

The test suite uses factory patterns for consistent test data creation:

```python
# Conversation factories
conversation = conversation_factory(
    chatwoot_conversation_id="test_123",
    status="pending"
)

# Schema factories  
conversation_create = conversation_create_factory(
    chatwoot_conversation_id="test_123"
)

# Webhook factories
webhook = chatwoot_webhook_factory(
    conversation_id=123,
    content="Test message"
)
```

### Test Data Builder

For complex test scenarios, use the `TestDataBuilder`:

```python
from tests.test_utils import TestDataBuilder

builder = TestDataBuilder()
conversation = (builder
    .with_conversation_id("test_123")
    .with_status("pending") 
    .with_assignee(456)
    .build_conversation_model())
```

### Database Isolation

Each test gets a fresh database transaction that is automatically rolled back:

```python
async def test_isolated_data(async_session: AsyncSession):
    """Each test has isolated database state."""
    # Create test data
    conversation = Conversation(chatwoot_conversation_id="test")
    async_session.add(conversation)
    await async_session.commit()
    
    # Data automatically cleaned up after test
```

## Best Practices

### 1. **Use Appropriate Test Types**

- **Unit Tests**: Test individual functions with mocks
- **Integration Tests**: Test service interactions with real or mock external services  
- **End-to-End Tests**: Test complete workflows with database persistence

### 2. **Mock External Services**

```python
# Good: Mock external services for unit/integration tests
@patch('app.api.chatwoot.ChatwootHandler')
async def test_with_mock(mock_handler):
    mock_handler.return_value.get_teams.return_value = [{"id": 1, "name": "Test"}]
    # Test logic here
```

### 3. **Use Factories for Test Data**

```python
# Good: Use factories for consistent test data
webhook = chatwoot_webhook_factory(conversation_id=123)

# Avoid: Manual data creation
webhook_data = {
    "event": "message_created",
    "message_type": "incoming",
    # ... lots of manual setup
}
```

### 4. **Test Schema Validation**

```python
# Good: Validate schemas explicitly
conversation_response = ConversationResponse.model_validate(response_data)

# Also good: Use assertion helpers
assert_conversation_response_valid(response_data)
```

### 5. **Clean Database State**

```python
# Good: Use fixtures that automatically clean up
async def test_with_cleanup(async_session: AsyncSession, sample_conversation):
    # Test uses existing fixtures with automatic cleanup
    pass

# For manual cleanup when needed
async def test_manual_cleanup(async_session: AsyncSession):
    conversation_ids = ["test_1", "test_2", "test_3"]
    # ... create test data ...
    await cleanup_test_conversations(async_session, conversation_ids)
```

## Debugging Tests

### 1. **Verbose Output**

```bash
pytest -v -s  # Show print statements and verbose output
```

### 2. **Database Inspection**

```python
# Add debugging prints in tests
async def test_debug_database(async_session: AsyncSession):
    # Create conversation
    conversation = Conversation(chatwoot_conversation_id="debug_test")
    async_session.add(conversation)
    await async_session.commit()
    
    # Debug: Check database state
    from sqlalchemy import select
    result = await async_session.execute(select(Conversation))
    all_conversations = result.scalars().all()
    print(f"Conversations in DB: {len(all_conversations)}")
```

### 3. **Mock Verification**

```python
async def test_mock_verification(mock_chatwoot_handler):
    await mock_chatwoot_handler.get_teams()
    
    # Verify mock interactions
    mock_chatwoot_handler.get_teams.assert_called_once()
    print(f"Mock call args: {mock_chatwoot_handler.get_teams.call_args}")
```

## Migration from Legacy Tests

### Key Changes

1. **SQLModel → SQLAlchemy 2**: Replace SQLModel imports with new model imports
2. **Sync → Async**: All database operations now use async sessions
3. **Manual Transactions → Automatic**: Transaction management is now automatic
4. **Pydantic v1 → v2**: Updated schema validation patterns
5. **Manual Mocks → Factory Patterns**: Consistent test data via factories

### Migration Checklist

- [ ] Update imports to use new models and schemas
- [ ] Replace `Session` with `AsyncSession` 
- [ ] Add `async`/`await` to database operations
- [ ] Update schema validation to use `model_validate()`
- [ ] Replace manual test data with factory functions
- [ ] Update mock patterns to use `AsyncMock`
- [ ] Add proper async test markers (`@pytest.mark.asyncio`)

## Performance Considerations

### 1. **Parallel Test Execution**

```bash
# Run tests in parallel (requires pytest-xdist)
pytest -n auto
```

### 2. **Test Isolation**

- Each test gets a fresh database transaction
- Automatic rollback ensures no test interference  
- In-memory SQLite provides fast test database

### 3. **Mock vs Real Services**

- Use mocks for unit tests (fastest)
- Use real services for integration tests (when needed)
- Use test doubles for external dependencies

## Troubleshooting

### Common Issues

1. **"RuntimeError: Event loop is closed"**
   - Ensure proper async test configuration in `pytest.ini`
   - Use `pytest-asyncio` with `asyncio_mode = auto`

2. **"Database session errors"**
   - Check that fixtures are properly scoped
   - Verify transaction rollback in test fixtures

3. **"Schema validation errors"**
   - Update to Pydantic v2 validation methods
   - Check field names match new schema definitions

4. **"Mock not working"**
   - Verify you're using `AsyncMock` for async methods
   - Check mock target path is correct

### Getting Help

1. Check test logs with `pytest -v -s`
2. Review the test utilities in `test_utils.py`
3. Look at existing test patterns in test files
4. Verify environment variables are set correctly

## Future Enhancements

- **Property-based Testing**: Add Hypothesis for property-based test generation
- **Performance Testing**: Add load testing for API endpoints
- **Contract Testing**: Add Pact testing for external service contracts
- **Visual Testing**: Add screenshot testing for UI components
- **Mutation Testing**: Add mutation testing for test quality verification 