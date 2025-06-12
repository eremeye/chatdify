"""SQLAlchemy 2 Base class with automatic dataclass mapping."""
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(MappedAsDataclass, DeclarativeBase):
    """
    Base class for all database models.
    
    Uses MappedAsDataclass to automatically generate dataclass functionality
    for all model classes that inherit from this base.
    """
    pass 