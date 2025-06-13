"""Database session configuration and utilities for SQLAlchemy 2."""
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app import config

# Synchronous engine for Celery tasks and migrations
sync_engine = create_engine(
    config.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=config.DB_POOL_SIZE,
    max_overflow=config.DB_MAX_OVERFLOW,
    pool_timeout=config.DB_POOL_TIMEOUT,
    pool_recycle=config.DB_POOL_RECYCLE,
    pool_pre_ping=config.DB_POOL_PRE_PING,
    connect_args={"connect_timeout": 10},  # PostgreSQL specific - connect timeout in seconds
)

# Async engine for FastAPI endpoints
# Convert the DATABASE_URL to async URL by replacing postgresql:// with postgresql+asyncpg://
async_database_url = config.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
async_engine = create_async_engine(
    async_database_url,
    pool_size=config.DB_POOL_SIZE,
    max_overflow=config.DB_MAX_OVERFLOW,
    pool_recycle=config.DB_POOL_RECYCLE,
    pool_pre_ping=config.DB_POOL_PRE_PING,
    pool_timeout=config.DB_POOL_TIMEOUT,
)

# Session makers with proper typing
SyncSessionLocal = sessionmaker(bind=sync_engine, class_=Session)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession)


# Sync session for Celery tasks
@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """Provide a synchronous session for Celery tasks."""
    with SyncSessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


# Main async session dependency following the six-line pattern
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async database session with automatic transaction management.
    
    This follows the recommended six-line async session pattern:
    1. Create session
    2. Begin transaction automatically
    3. Yield session
    4. Handle exceptions (rollback handled automatically by session.begin())
    5. Commit on success (handled automatically by session.begin())
    6. Close session automatically
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session


# Alternative async session context manager
@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session context manager for programmatic use."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session


# Legacy compatibility functions
@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Legacy sync session - use get_sync_session() instead."""
    with get_sync_session() as session:
        yield session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Legacy async session dependency - use get_session() instead."""
    async for session in get_session():
        yield session 