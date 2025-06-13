# SQLAlchemy 2 Foundation Layer

This module provides the core database infrastructure for the Chatdify application using SQLAlchemy 2.x with modern async/await patterns, automatic transaction management, and the six-line session pattern.

## Architecture

The database layer is organized into the following modules:

- `base.py` - Core Base class with MappedAsDataclass
- `session.py` - Engine configuration and session management with six-line pattern
- `utils.py` - Database utilities and table management
- `models.py` - Database model definitions
- `__init__.py` - Clean import interface

## Session Management (Updated in Task 5)

The session management has been refactored to use the recommended **six-line async session pattern** with automatic transaction management.

### Six-Line Pattern Implementation

```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Six-line async session pattern:
    1. Create session
    2. Begin transaction automatically
    3. Yield session
    4. Handle exceptions (rollback handled automatically)
    5. Commit on success (handled automatically)
    6. Close session automatically
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session
```

### Database Sessions

#### Async Sessions (FastAPI Dependencies)

**✅ New Pattern ** - Use the updated session dependency:

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session

async def my_endpoint(session: AsyncSession = Depends(get_session)):
    # Automatic transaction management - no manual commit/rollback needed
    result = await session.execute(select(MyModel))
    return result.scalars().all()
```

**⚠️ Legacy Pattern (Deprecated)** - Still works but deprecated:

```python
from app.database import get_db  # Deprecated - use app.db.session instead
```

#### Sync Sessions (Celery Tasks)

**✅ Updated Pattern (Task 5)** - Use the refined sync session:

```python
from app.db.session import get_sync_session

@celery_app.task
def my_task():
    with get_sync_session() as session:
        # Automatic transaction management
        # Commit on success, rollback on exception
        result = session.execute(select(MyModel))
        return result.scalars().all()
```

#### Context Manager for Programmatic Use

```python
from app.db.session import get_async_session

async def some_function():
    async with get_async_session() as session:
        # Automatic transaction management
        result = await session.execute(select(MyModel))
        return result.scalars().all()
```

## Usage

### Import the Base Class

For new models, use the SQLAlchemy 2 Base class:

```python
from app.db import Base
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class MyModel(Base):
    __tablename__ = "my_table"
    
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    name: Mapped[str] = mapped_column(String(50))
```

### Transaction Management

**Implementation** - Automatic transaction management:

- **Six-line pattern**: `AsyncSessionLocal() → session.begin() → yield session`
- **Automatic transactions**: No manual commit/rollback required
- **Exception handling**: Built-in rollback on exceptions
- **Session cleanup**: Automatic session disposal

### Table Creation

```python
from app.db.utils import create_db_tables

# Async version (used in FastAPI lifespan)
await create_db_tables()
```

## Migration from Legacy Session Management

The session management refactoring maintains backward compatibility:

### Import Migration

**✅ New Imports (Recommended):**
```python
from app.db.session import get_session, get_sync_session, get_async_session
from app.db.session import async_engine, sync_engine
```

**⚠️ Legacy Imports (Deprecated but still work):**
```python
from app.database import get_db, get_session, SessionLocal  # Deprecated
```

### API Endpoint Migration

**Before (Legacy):**
```python
from app.database import get_db
from sqlmodel import Session

async def endpoint(db: Session = Depends(get_db)):
    # Manual transaction management required
    try:
        # database operations
        db.commit()
    except:
        db.rollback()
        raise
```

**After:**
```python
from app.db.session import get_session
from sqlalchemy.ext.asyncio import AsyncSession

async def endpoint(db: AsyncSession = Depends(get_session)):
    # Automatic transaction management
    # database operations - no manual commit/rollback needed
```

### Celery Task Migration

**Before (Legacy):**
```python
from app.database import SessionLocal

def my_task():
    with SessionLocal() as db:
        try:
            # operations
            db.commit()
        except:
            db.rollback()
            raise
```

**After (Task 5):**
```python
from app.db.session import get_sync_session

def my_task():
    with get_sync_session() as db:
        # Automatic transaction management
        # operations
```

## Model Migration from SQLModel

### Legacy SQLModel Pattern

```python
from sqlmodel import SQLModel, Field

class MyModel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
```

### New SQLAlchemy 2 Pattern

```python
from app.db import Base
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class MyModel(Base):
    __tablename__ = "my_model"  # Required in SQLAlchemy 2
    
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    name: Mapped[str] = mapped_column(String(50))
```

## Configuration

Database configuration is managed through environment variables in `app.config`:

- `DB_POOL_SIZE` - Connection pool size (default: 10)
- `DB_MAX_OVERFLOW` - Max pool overflow (default: 20)  
- `DB_POOL_TIMEOUT` - Pool timeout in seconds (default: 30)
- `DB_POOL_RECYCLE` - Connection recycle time (default: 1800)
- `DB_POOL_PRE_PING` - Enable connection health checks (default: True)

## Engine Access

Both engines are available for direct access if needed:

```python
from app.db.session import async_engine, sync_engine

# Use for Alembic migrations, raw queries, health checks, etc.
```

## Best Practices

1. **✅ Use the new session patterns** - `get_session()` for FastAPI, `get_sync_session()` for Celery
2. **✅ Use dependency injection** for FastAPI endpoints with proper type hints
3. **✅ Let the framework handle transactions** - don't manually commit/rollback
4. **✅ Use the new Base class** for all new models with explicit `__tablename__`
5. **✅ Import from app.db.session** for new code, not app.database
6. **✅ Use async/await patterns** consistently in async contexts
7. **✅ Separate sync and async sessions** - don't mix them

## Task 5 Completion Summary

### ✅ What Was Implemented

- **Six-line session pattern** with automatic transaction management
- **Updated dependency injection** across all API endpoints (9 endpoints in webhooks.py, health.py)
- **Refined Celery task sessions** with automatic commit/rollback
- **Legacy compatibility layer** maintained in app.database
- **Proper type hints** with AsyncSession throughout
- **Consistent error handling** with automatic rollback on exceptions

### 📁 Files Updated

- `app/db/session.py` - Core session implementation
- `app/api/health.py` - Health endpoints
- `app/api/webhooks.py` - All webhook endpoints  
- `app/tasks.py` - Celery background tasks
- `app/database.py` - Legacy compatibility

## Troubleshooting

### Common Issues

1. **"Undefined name 'get_db'"**: Update imports to use `from app.db.session import get_session`
2. **Transaction errors**: The new pattern handles transactions automatically
3. **Session type errors**: Use `AsyncSession` type hints with async endpoints
4. **Import errors**: Use `from app.db.session import ...` for new infrastructure

### Debugging

Enable SQLAlchemy logging to debug issues:

```python
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

### Verification

To verify the session patterns are working:

```python
# Test async session pattern
from app.db.session import get_session
async for session in get_session():
    result = await session.execute(text("SELECT 1"))
    print(result.scalar())  # Should print 1
    break

# Test sync session pattern  
from app.db.session import get_sync_session
with get_sync_session() as session:
    result = session.execute(text("SELECT 1"))
    print(result.scalar())  # Should print 1
``` 