# SQLAlchemy 2 Foundation Layer

This module provides the core database infrastructure for the Chatdify application using SQLAlchemy 2.x with modern async/await patterns and automatic dataclass generation.

## Architecture

The database layer is organized into the following modules:

- `base.py` - Core Base class with MappedAsDataclass
- `session.py` - Engine configuration and session management  
- `utils.py` - Database utilities and table management
- `__init__.py` - Clean import interface

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

### Database Sessions

#### Async Sessions (FastAPI Dependencies)

For FastAPI endpoints, use the async session dependency:

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session

async def my_endpoint(session: AsyncSession = Depends(get_session)):
    # Use session here - transaction is automatic
    result = await session.execute(select(MyModel))
    return result.scalars().all()
```

#### Sync Sessions (Celery Tasks)

For Celery tasks, use the sync session:

```python
from app.db import get_sync_session

@celery_app.task
def my_task():
    with get_sync_session() as session:
        # Use session here - transaction is automatic
        result = session.execute(select(MyModel))
        return result.scalars().all()
```

### Transaction Management

The new session infrastructure uses automatic transaction management:

- **Async sessions**: Use `async with session.begin()` pattern internally
- **Sync sessions**: Use `session.commit()` on success, `session.rollback()` on exception
- **Automatic cleanup**: Sessions are automatically closed after use

### Table Creation

```python
from app.db import create_tables, create_tables_async

# Sync version
create_tables()

# Async version  
await create_tables_async()
```

## Migration from SQLModel

The foundation layer maintains backward compatibility with existing SQLModel code:

### Legacy Imports Still Work

```python
# These still work but are deprecated
from app.database import get_db, get_session, SessionLocal
```

### Gradual Migration Path

1. **Phase 1**: Use new `app.db` imports for new code
2. **Phase 2**: Migrate existing models to new Base class  
3. **Phase 3**: Remove legacy imports

### Model Migration Example

**Before (SQLModel):**
```python
from sqlmodel import SQLModel, Field

class MyModel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
```

**After (SQLAlchemy 2):**
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
from app.db import async_engine, sync_engine

# Use for Alembic migrations, raw queries, etc.
```

## Best Practices

1. **Use dependency injection** for FastAPI endpoints
2. **Use context managers** for programmatic database access
3. **Let the framework handle transactions** - don't manually commit/rollback unless needed
4. **Use the new Base class** for all new models
5. **Import from app.db** for new code, not app.database

## Troubleshooting

### Common Issues

1. **"Table has no __tablename__"**: SQLAlchemy 2 requires explicit `__tablename__` attribute
2. **Transaction errors**: Ensure you're using the session patterns correctly
3. **Import errors**: Use `from app.db import ...` for new infrastructure

### Debugging

Enable SQLAlchemy logging to debug issues:

```python
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
``` 