"""
CHAI Database Package.
Provides asynchronous PostgreSQL persistence for conversations, messages, memories, and user profiles.
"""
from backend.db.database import (
    get_engine,
    init_db,
    get_session,
    normalize_database_url,
)
from backend.db.models import (
    Base,
    ConversationModel,
    MessageModel,
    MemoryModel,
    UserProfileModel,
)
from backend.db.repositories import (
    ConversationRepository,
    MessageRepository,
    MemoryRepository,
    UserProfileRepository,
)

__all__ = [
    "get_engine",
    "init_db",
    "get_session",
    "normalize_database_url",
    "Base",
    "ConversationModel",
    "MessageModel",
    "MemoryModel",
    "UserProfileModel",
    "ConversationRepository",
    "MessageRepository",
    "MemoryRepository",
    "UserProfileRepository",
]
