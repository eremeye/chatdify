"""Database utilities for SQLAlchemy 2 with backward compatibility."""
import logging

# Import models to register them with the metadata
import app.db.models  # noqa: F401

from .base import Base
from .session import async_engine, sync_engine

logger = logging.getLogger(__name__)


def create_tables():
    """
    Create all database tables using SQLAlchemy 2.
    
    This creates tables for the new SQLAlchemy 2 models that inherit from Base.
    """
    logger.info("Creating database tables...")
    try:
        # Create SQLAlchemy 2 tables from new Base
        Base.metadata.create_all(sync_engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise


def drop_tables():
    """
    Drop all database tables.
    
    WARNING: This will delete all data!
    """
    logger.warning("Dropping all database tables...")
    try:
        # Drop SQLAlchemy 2 tables
        Base.metadata.drop_all(sync_engine)
        logger.info("Database tables dropped successfully")
    except Exception as e:
        logger.error(f"Failed to drop database tables: {e}")
        raise


async def create_tables_async():
    """
    Create tables asynchronously at startup.
    
    Note: Uses sync engine as table creation is more reliable with sync operations.
    """
    logger.info("Starting async table creation...")
    try:
        create_tables()
        logger.info("Async table creation completed")
    except Exception as e:
        logger.error(f"Async table creation failed: {e}")
        raise


# Legacy function for backward compatibility
async def create_db_tables():
    """
    Legacy function - use create_tables_async() instead.
    Maintained for backward compatibility with existing code.
    """
    await create_tables_async() 