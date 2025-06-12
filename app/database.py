"""
Legacy database module - migrating to app.db package.

This module provides backward compatibility during the transition to SQLAlchemy 2.
New code should import from app.db instead.
"""
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session, SQLModel

# Import new infrastructure
from app.db.session import (
    async_engine,
    get_async_session,
    get_db as _get_db,
    get_sync_session,
    sync_engine,
)
from app.db.utils import create_db_tables as _create_db_tables

# Re-export for backward compatibility
__all__ = [
    "sync_engine",
    "async_engine", 
    "get_session",
    "SessionLocal",
    "get_async_db",
    "get_db",
    "create_db_tables",
]

# Legacy sync session for Celery tasks - redirect to new implementation
@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Provide a synchronous session for Celery tasks.
    
    DEPRECATED: Use app.db.session.get_sync_session() instead.
    """
    with get_sync_session() as session:
        yield session


# Keep this for backward compatibility
SessionLocal = get_session


# Legacy async session for FastAPI endpoints - redirect to new implementation
@asynccontextmanager
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async database session for FastAPI endpoints.
    
    DEPRECATED: Use app.db.session.get_async_session() instead.
    """
    async with get_async_session() as session:
        yield session


# For FastAPI dependency injection - redirect to new implementation
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for async database access.
    
    DEPRECATED: Use app.db.session.get_session() instead.
    """
    async for session in _get_db():
        yield session


async def create_db_tables():
    """
    Create tables asynchronously at startup.
    
    DEPRECATED: Use app.db.utils.create_tables_async() instead.
    """
    await _create_db_tables()
