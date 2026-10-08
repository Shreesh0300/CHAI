"""
Storage layer for CHAI memory architecture backed by PostgreSQL.
PostgreSQL is the durable source of truth for conversations, messages,
long-term memories, and user profiles.
Guarantees strict user isolation, guest session boundaries, and safe database error handling.
"""
import re
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from backend.shared.logger import get_logger
from backend.config import get_settings
from backend.memory.models import (
    MemoryItem,
    MemoryCategory,
    UserProfile,
    ChatMessageRecord,
    ConversationRecord,
)
from backend.db.database import init_db
from backend.db.repositories import (
    ConversationRepository,
    MessageRepository,
    MemoryRepository,
    UserProfileRepository,
)

logger = get_logger(__name__)

# Patterns that indicate secrets or credentials which must NEVER be stored
SENSITIVE_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z-_]{30,45}"),  # Google API key
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT token
    re.compile(r"(?:api[_-]?key|secret|password|bearer|auth[_-]?token)\s*(?:[:=]|\bis\b)\s*\S+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style key
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),  # GitHub token
]


def sanitize_sensitive_data(text: str) -> str:
    """Removes API keys, tokens, and passwords from stored memory text."""
    sanitized = text
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized


def is_guest_user(user_id: Optional[str]) -> bool:
    """Determines whether a user identifier belongs to an ephemeral guest session."""
    if not user_id:
        return True
    uid = user_id.lower().strip()
    return uid.startswith("guest") or "guest@" in uid or uid == "operator@chai.ai"


class MemoryStore:
    """
    Central storage service for CHAI user memory and conversation records.
    PostgreSQL is the durable source of truth.
    Thread-safe in-memory cache acts as an operational performance layer.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        # In-memory performance cache partitioned by user_id -> Dict[memory_id, MemoryItem]
        self._memories_cache: Dict[str, Dict[str, MemoryItem]] = {}
        # In-memory performance cache partitioned by user_id -> UserProfile
        self._profiles_cache: Dict[str, UserProfile] = {}
        # In-memory performance cache partitioned by conversation_id -> List[ChatMessageRecord]
        self._messages_cache: Dict[str, List[ChatMessageRecord]] = {}
        # Ephemeral guest session partitions (session_id -> memory list)
        self._guest_memories: Dict[str, List[MemoryItem]] = {}
        self._db_ready: bool = False

    async def _ensure_db(self) -> None:
        """Lazily verifies database initialization."""
        if not self._db_ready:
            try:
                await init_db()
                self._db_ready = True
            except Exception as exc:
                logger.warning(f"[MEMORY STORE] Database init check skipped or delayed: {exc}")

    # =========================================================================
    # Level B: Long-Term Memories
    # =========================================================================

    async def add_memory(
        self,
        user_id: str,
        memory: str,
        category: MemoryCategory = MemoryCategory.GENERAL,
        importance: int = 3,
        session_id: Optional[str] = None,
    ) -> MemoryItem:
        """
        Stores a durable memory item into PostgreSQL (or session partition for guests).
        """
        cleaned_memory = sanitize_sensitive_data(memory.strip())
        if not cleaned_memory:
            raise ValueError("Memory text cannot be empty.")

        item = MemoryItem(
            user_id=user_id,
            memory=cleaned_memory,
            category=category,
            importance=max(1, min(5, importance)),
        )

        async with self._lock:
            # 1. Ephemeral guest session scoping
            if is_guest_user(user_id):
                guest_key = session_id or user_id
                if guest_key not in self._guest_memories:
                    self._guest_memories[guest_key] = []
                self._guest_memories[guest_key].append(item)
                logger.info(f"[MEMORY STORE] Stored guest session memory for {guest_key}: {item.memory[:50]}...")
                return item

            # 2. Update in-memory cache
            if user_id not in self._memories_cache:
                self._memories_cache[user_id] = {}
            self._memories_cache[user_id][item.id] = item

            # 3. Persist to PostgreSQL as durable source of truth
            try:
                await self._ensure_db()
                db_model = await MemoryRepository.save_memory(
                    user_id=user_id,
                    memory=item.memory,
                    category=item.category.value if hasattr(item.category, "value") else str(item.category),
                    importance=item.importance,
                    memory_id=item.id,
                )
                item.id = db_model.id
                item.created_at = db_model.created_at
                item.updated_at = db_model.updated_at
                self._memories_cache[user_id][item.id] = item
                logger.info(f"[MEMORY STORE] Persisted memory to PostgreSQL for user {user_id}: {item.memory[:50]}...")
            except Exception as exc:
                # Requirement 15: Database failure must not crash chat turn
                logger.error(f"[MEMORY STORE] Failed to persist memory to PostgreSQL: {exc}")

            return item

    async def get_user_memories(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[MemoryItem]:
        """
        Retrieves memories strictly belonging to user_id from PostgreSQL.
        User A can never see User B's memories.
        """
        async with self._lock:
            # Guest lookup
            if is_guest_user(user_id):
                guest_key = session_id or user_id
                return list(self._guest_memories.get(guest_key, []))[:limit]

            # Primary: Query PostgreSQL durable storage
            try:
                await self._ensure_db()
                db_models = await MemoryRepository.get_user_memories(user_id=user_id, limit=limit)
                if db_models:
                    items: List[MemoryItem] = []
                    for m in db_models:
                        try:
                            cat = MemoryCategory(m.category)
                        except Exception:
                            cat = MemoryCategory.GENERAL
                        items.append(MemoryItem(
                            id=m.id,
                            user_id=m.user_id,
                            memory=m.memory,
                            category=cat,
                            importance=m.importance,
                            created_at=m.created_at,
                            updated_at=m.updated_at,
                        ))
                    # Sync cache
                    if user_id not in self._memories_cache:
                        self._memories_cache[user_id] = {}
                    for item in items:
                        self._memories_cache[user_id][item.id] = item
                    return items
            except Exception as exc:
                logger.warning(f"[MEMORY STORE] PostgreSQL retrieval error ({exc}); using cache fallback.")

            # Fallback to in-memory cache
            cached_items = list(self._memories_cache.get(user_id, {}).values())
            cached_items.sort(key=lambda x: (x.importance, x.updated_at), reverse=True)
            return cached_items[:limit]

    async def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """Deletes a memory item belonging strictly to user_id from PostgreSQL."""
        async with self._lock:
            # Remove from cache
            if user_id in self._memories_cache and memory_id in self._memories_cache[user_id]:
                del self._memories_cache[user_id][memory_id]

            # Delete from PostgreSQL
            try:
                await self._ensure_db()
                return await MemoryRepository.delete_memory(user_id=user_id, memory_id=memory_id)
            except Exception as exc:
                logger.error(f"[MEMORY STORE] Failed to delete memory from PostgreSQL: {exc}")
                return False

    async def clear_user_memories(self, user_id: str) -> None:
        """Clears all memories for a specific user (for test isolation and privacy)."""
        async with self._lock:
            if user_id in self._memories_cache:
                self._memories_cache[user_id].clear()
            if user_id in self._guest_memories:
                self._guest_memories[user_id].clear()

            try:
                await self._ensure_db()
                await MemoryRepository.clear_user_memories(user_id=user_id)
            except Exception as exc:
                logger.error(f"[MEMORY STORE] Failed to clear user memories in PostgreSQL: {exc}")

    # =========================================================================
    # Level C: User Profile & Preferences
    # =========================================================================

    async def get_or_create_profile(self, user_id: str, name: Optional[str] = None, email: Optional[str] = None) -> UserProfile:
        """Gets or initializes the user profile in PostgreSQL."""
        async with self._lock:
            try:
                await self._ensure_db()
                db_profile = await UserProfileRepository.get_or_create_profile(user_id, name=name, email=email)
                profile = UserProfile(
                    user_id=db_profile.user_id,
                    name=db_profile.name or ("Guest" if is_guest_user(user_id) else user_id),
                    email=db_profile.email,
                    role=db_profile.role,
                    goals=db_profile.goals or [],
                    interests=db_profile.interests or [],
                    preferences=db_profile.preferences or {},
                    updated_at=db_profile.updated_at,
                )
                self._profiles_cache[user_id] = profile
                return profile
            except Exception as exc:
                logger.warning(f"[MEMORY STORE] Profile fetch from PostgreSQL error ({exc}); using cache fallback.")

            if user_id not in self._profiles_cache:
                self._profiles_cache[user_id] = UserProfile(
                    user_id=user_id,
                    name=name or ("Guest" if is_guest_user(user_id) else user_id),
                    email=email,
                )
            return self._profiles_cache[user_id]

    async def update_profile(self, user_id: str, profile_update: Dict[str, Any]) -> UserProfile:
        """Updates user preferences, goals, or role in PostgreSQL."""
        async with self._lock:
            try:
                await self._ensure_db()
                db_profile = await UserProfileRepository.update_profile(user_id, profile_update)
                profile = UserProfile(
                    user_id=db_profile.user_id,
                    name=db_profile.name,
                    email=db_profile.email,
                    role=db_profile.role,
                    goals=db_profile.goals or [],
                    interests=db_profile.interests or [],
                    preferences=db_profile.preferences or {},
                    updated_at=db_profile.updated_at,
                )
                self._profiles_cache[user_id] = profile
                return profile
            except Exception as exc:
                logger.error(f"[MEMORY STORE] Failed to update profile in PostgreSQL: {exc}")

            profile = self._profiles_cache.get(user_id)
            if not profile:
                profile = UserProfile(user_id=user_id)
                self._profiles_cache[user_id] = profile

            if "name" in profile_update and profile_update["name"]:
                profile.name = profile_update["name"]
            if "role" in profile_update and profile_update["role"]:
                profile.role = profile_update["role"]
            if "goals" in profile_update and isinstance(profile_update["goals"], list):
                profile.goals = profile_update["goals"]
            if "interests" in profile_update and isinstance(profile_update["interests"], list):
                profile.interests = profile_update["interests"]
            if "preferences" in profile_update and isinstance(profile_update["preferences"], dict):
                profile.preferences.update(profile_update["preferences"])
            profile.updated_at = datetime.now(timezone.utc).isoformat()
            return profile

    # =========================================================================
    # Level A: Short-Term Conversation Messages
    # =========================================================================

    async def add_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
    ) -> ChatMessageRecord:
        """Appends a message to PostgreSQL conversation history and cache."""
        cleaned_content = sanitize_sensitive_data(content)
        msg = ChatMessageRecord(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=cleaned_content,
        )

        async with self._lock:
            # Cache update
            if conversation_id not in self._messages_cache:
                self._messages_cache[conversation_id] = []
            self._messages_cache[conversation_id].append(msg)

            # Persist to PostgreSQL
            try:
                await self._ensure_db()
                db_msg = await MessageRepository.save_message(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    role=role,
                    content=cleaned_content,
                    message_id=msg.id,
                )
                msg.id = db_msg.id
                msg.created_at = db_msg.created_at
            except Exception as exc:
                logger.error(f"[MEMORY STORE] Failed to save message to PostgreSQL: {exc}")

            return msg

    async def get_recent_messages(
        self,
        conversation_id: str,
        user_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[ChatMessageRecord]:
        """
        Retrieves recent messages from PostgreSQL conversation history.
        Enforces user ownership.
        """
        async with self._lock:
            try:
                await self._ensure_db()
                db_msgs = await MessageRepository.get_recent_messages(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    limit=limit,
                )
                if db_msgs:
                    return [
                        ChatMessageRecord(
                            id=m.id,
                            conversation_id=m.conversation_id,
                            user_id=m.user_id,
                            role=m.role,
                            content=m.content,
                            created_at=m.created_at,
                        )
                        for m in db_msgs
                    ]
            except Exception as exc:
                logger.warning(f"[MEMORY STORE] PostgreSQL get_recent_messages error ({exc}); using cache fallback.")

            # Fallback to cache
            cached_msgs = self._messages_cache.get(conversation_id, [])
            if not cached_msgs:
                return []
            if user_id:
                first_msg = cached_msgs[0]
                if first_msg.user_id != user_id:
                    logger.warning(f"[SECURITY] User {user_id} attempted to access conversation {conversation_id} owned by {first_msg.user_id}")
                    return []
            return cached_msgs[-limit:]

    async def list_user_conversations(self, user_id: str) -> List[ConversationRecord]:
        """Returns all conversations owned strictly by user_id from PostgreSQL."""
        async with self._lock:
            try:
                await self._ensure_db()
                db_convos = await ConversationRepository.list_conversations(user_id=user_id)
                return [
                    ConversationRecord(
                        id=c.id,
                        user_id=c.user_id,
                        title=c.title,
                        created_at=c.created_at,
                        updated_at=c.updated_at,
                    )
                    for c in db_convos
                ]
            except Exception as exc:
                logger.error(f"[MEMORY STORE] Failed to list conversations from PostgreSQL: {exc}")
                return []


# Global singleton instance
memory_store = MemoryStore()
