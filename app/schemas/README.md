# Pydantic v2 DTO Schemas

This directory contains all Data Transfer Object (DTO) schemas built with Pydantic v2 for the Chatdify application. These schemas provide type-safe, validated data structures for API requests/responses, database operations, and external service integrations.

## 📁 Directory Structure

```
app/schemas/
├── __init__.py          # Central exports for all schemas
├── conversation.py      # Conversation-related DTOs
├── chatwoot.py         # Chatwoot webhook integration DTOs  
├── dify.py             # Dify AI service integration DTOs
└── README.md           # This documentation
```

## 🏗️ Schema Organization

### Conversation Schemas (`conversation.py`)

**Purpose**: Handle conversation data for database operations and API endpoints.

| Schema | Usage | Description |
|--------|-------|-------------|
| `ConversationBase` | Base class | Common fields for all conversation schemas |
| `ConversationCreate` | Database ops | Internal schema for creating conversations |
| `ConversationCreateRequest` | API requests | Validates incoming POST requests |
| `ConversationUpdateRequest` | API requests | Validates PATCH/PUT requests |
| `ConversationResponse` | API responses | Serializes conversation data for clients |
| `ConversationPriority` | Enum | Priority levels (urgent, high, medium, low) |
| `ConversationStatus` | Enum | Status values (open, resolved, pending) |

### Chatwoot Integration Schemas (`chatwoot.py`)

**Purpose**: Process webhook payloads and external API communication with Chatwoot.

| Schema | Usage | Description |
|--------|-------|-------------|
| `ChatwootSender` | Webhook parsing | Message sender information |
| `ChatwootMeta` | Webhook parsing | Conversation metadata with computed properties |
| `ChatwootConversation` | Webhook parsing | Conversation data from Chatwoot |
| `ChatwootMessage` | Webhook parsing | Individual message data |
| `ChatwootWebhook` | Webhook endpoint | Complete webhook payload validation |

### Dify Integration Schemas (`dify.py`)

**Purpose**: Handle AI service responses and error management.

| Schema | Usage | Description |
|--------|-------|-------------|
| `DifyResponse` | AI processing | Validates and processes Dify AI responses |

## 🔧 Pydantic v2 Features Used

### Configuration
All schemas use `ConfigDict(from_attributes=True)` for seamless ORM integration:

```python
class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

### Computed Fields
Dynamic properties using `@computed_field` decorator:

```python
@computed_field
@property
def is_assigned(self) -> bool:
    """Check if conversation has an assigned agent."""
    return self.assignee_id is not None
```

### Field Validation
Input validation with `@field_validator`:

```python
@field_validator("answer")
@classmethod
def validate_answer_not_empty(cls, v: str) -> str:
    if not v or not v.strip():
        raise ValueError("Answer cannot be empty or whitespace-only")
    return v.strip()
```

## 🚀 Usage Patterns

### Method Reference Table

| Input Type | Method | Example |
|------------|--------|---------|
| JSON string | `model_validate_json()` | `Model.model_validate_json('{"id": 1}')` |
| JSON bytes | `model_validate_json()` | `Model.model_validate_json(b'{"id": 1}')` |
| Python dict | `model_validate()` | `Model.model_validate({"id": 1})` |
| Object with attributes | `model_validate()` | `Model.model_validate(db_instance)` |

### 1. Converting JSON/Dict to DTO

**Webhook Processing (from dict):**
```python
from app.schemas import ChatwootWebhook

# Validate incoming webhook payload (already parsed to dict)
payload = await request.json()  # This returns a Python dict
webhook_data = ChatwootWebhook.model_validate(payload)
```

**API Response Processing (from JSON string):**
```python
from app.schemas import DifyResponse

# Validate JSON string directly
json_response = requests.get("https://api.dify.ai/...").text
dify_response = DifyResponse.model_validate_json(json_response)

# Or from parsed dict
response_dict = requests.get("https://api.dify.ai/...").json()
dify_response = DifyResponse.model_validate(response_dict)
```

### 2. Converting Database Models to DTOs

**Single Model:**
```python
from app.schemas import ConversationResponse
from app.db.models import Conversation

conversation = await db.get(Conversation, conversation_id)
response_dto = ConversationResponse.model_validate(conversation)
```

**API Endpoint Response:**
```python
@router.get("/conversations/{id}")
async def get_conversation(id: int, db: AsyncSession = Depends(get_db)):
    conversation = await db.get(Conversation, id)
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    
    response_dto = ConversationResponse.model_validate(conversation)
    return response_dto.model_dump()
```

### 3. Converting DTOs to Database Models

**Create Operations:**
```python
from app.schemas import ConversationCreate
from app.db.models import Conversation

# From validated DTO to database model
conversation_data = ConversationCreate(
    chatwoot_conversation_id="123",
    status="pending"
)
db_conversation = Conversation(**conversation_data.model_dump())
db.add(db_conversation)
```

**Update Operations:**
```python
from app.schemas import ConversationUpdateRequest

# Partial updates with exclude_unset
update_data = ConversationUpdateRequest(status="resolved")
for field, value in update_data.model_dump(exclude_unset=True).items():
    setattr(conversation, field, value)
```

### 4. API Request Validation

**POST Endpoints:**
```python
@router.post("/conversations/")
async def create_conversation(
    request: ConversationCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    # Request is automatically validated by FastAPI
    conversation = Conversation(**request.model_dump())
    db.add(conversation)
    await db.commit()
    
    # Return typed response
    response = ConversationResponse.model_validate(conversation)
    return response.model_dump()
```

**PATCH Endpoints:**
```python
@router.patch("/conversations/{id}")
async def update_conversation(
    id: int,
    updates: ConversationUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    conversation = await db.get(Conversation, id)
    
    # Apply only provided fields
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(conversation, field, value)
    
    await db.commit()
    response = ConversationResponse.model_validate(conversation)
    return response.model_dump()
```

## 🎯 Best Practices

### ✅ Do's

1. **Use `model_validate_json()`** for JSON strings and `model_validate()` for Python dicts/objects
2. **Use `model_dump()`** for serialization, not manual dict construction
3. **Use `exclude_unset=True`** for partial updates (PATCH operations)
4. **Use `exclude_none=True`** for clean API responses
5. **Leverage computed fields** for derived properties
6. **Use proper type hints** for better IDE support

### ❌ Don'ts

1. **Don't create custom wrapper methods** like `from_dict()`
2. **Don't use deprecated methods** like `.dict()` or `.json()`
3. **Don't bypass validation** with direct instantiation from unvalidated data
4. **Don't manually construct dictionaries** when DTOs exist
5. **Don't mix old Pydantic v1 patterns** with v2 code

### Serialization Options

```python
# Full serialization
data = schema.model_dump()

# Exclude None values (clean API responses)  
data = schema.model_dump(exclude_none=True)

# Exclude unset fields (partial updates)
data = schema.model_dump(exclude_unset=True)

# Custom field exclusion
data = schema.model_dump(exclude={'internal_field'})

# Include only specific fields
data = schema.model_dump(include={'id', 'name', 'status'})
```

## 🔄 Migration from Old Patterns

### Before (app/models/non_database.py)
```python
# Old scattered approach
from app.models.non_database import ChatwootWebhook, ConversationCreate

# Manual instantiation (less safe)
webhook = ChatwootWebhook(**payload)
```

### After (app/schemas/)
```python
# New organized approach
from app.schemas import ChatwootWebhook, ConversationCreate, ConversationResponse

# Validated conversion (safer)
webhook = ChatwootWebhook.model_validate(payload)
```

## 🧪 Testing Patterns

### Schema Validation Testing
```python
def test_conversation_create_validation():
    # Valid data
    valid_data = {
        "chatwoot_conversation_id": "123",
        "status": "pending"
    }
    conversation = ConversationCreate.model_validate(valid_data)
    assert conversation.status == "pending"
    
    # Invalid data
    with pytest.raises(ValidationError):
        ConversationCreate.model_validate({"invalid": "data"})
```

### Database Integration Testing
```python
def test_database_conversion():
    # Create database model
    db_conversation = Conversation(
        chatwoot_conversation_id="123",
        status="open"
    )
    
    # Convert to response DTO
    response = ConversationResponse.model_validate(db_conversation)
    
    # Verify computed fields work
    assert response.is_assigned == False
    assert response.has_dify_integration == False
```

## 📚 Import Guide

### Central Import (Recommended)
```python
from app.schemas import (
    ConversationCreate,
    ConversationResponse,
    ChatwootWebhook,
    DifyResponse
)
```

### Direct Module Import (When Needed)
```python
from app.schemas.conversation import ConversationPriority, ConversationStatus
from app.schemas.chatwoot import ChatwootSender, ChatwootMeta
```

## 🔗 Related Documentation

- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [FastAPI with Pydantic](https://fastapi.tiangolo.com/tutorial/body/)
- [SQLAlchemy 2 Integration](../db/README.md)

## 🚨 Breaking Changes

This DTO structure replaces the previous `app/models/non_database.py` approach. All imports have been updated, but if you're extending the codebase:

- **Old**: `from app.models.non_database import ConversationCreate`
- **New**: `from app.schemas import ConversationCreate`

The API remains functionally identical, but the internal structure is now more organized and type-safe. 