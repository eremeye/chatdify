"""Database utilities for SQLAlchemy 2 and SQLModel compatibility."""
from sqlmodel import SQLModel

from .base import Base
from .session import sync_engine


def create_tables():
    """
    Create all database tables.
    
    This creates tables for both SQLModel (backward compatibility)
    and new SQLAlchemy 2 models that inherit from the new Base.
    """
    # Create SQLModel tables (for backward compatibility)
    SQLModel.metadata.create_all(sync_engine)
    
    # Create SQLAlchemy 2 tables from new Base
    Base.metadata.create_all(sync_engine)


def drop_tables():
    """
    Drop all database tables.
    
    WARNING: This will delete all data!
    """
    # Drop SQLAlchemy 2 tables
    Base.metadata.drop_all(sync_engine)
    
    # Drop SQLModel tables
    SQLModel.metadata.drop_all(sync_engine)


async def create_tables_async():
    """
    Create tables asynchronously at startup.
    
    Note: Uses sync engine as table creation is more reliable with sync operations.
    """
    create_tables()


# Legacy function for backward compatibility
async def create_db_tables():
    """
    Legacy function - use create_tables_async() instead.
    """
    await create_tables_async() 