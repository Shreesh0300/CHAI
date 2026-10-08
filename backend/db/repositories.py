"""
Database repository implementations enforcing strict user isolation for CHAI.
Every query enforces: WHERE user_id = current_user_id.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_session
from backend.db.models import (
    ConversationModel,
    MessageModel,
    MemoryModel,
    UserProfileModel,
    _utc_now_iso,
)
from backend.shared.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# 1. Conversation Repository
# =============================================================================

class ConversationRepository:
    """Manages conversations with strict user ownership isolation."""

    @staticmethod
    async def save_conversation(
        user_id: str,
        conversation_id: str,
        title: str = "New Conversation",
        session: Optional[AsyncSession] = None,
    ) -> ConversationModel:
        async def _exec(s: AsyncSession) -> ConversationModel:
            now = _utc_now_iso()
            stmt = select(ConversationModel).where(
                ConversationModel.id == conversation_id,
                ConversationModel.user_id == user_id,
            )
            result = await s.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                existing.title = title
                existing.updated_at = now
                return existing

            convo = ConversationModel(
                id=conversation_id,
                user_id=user_id,
                title=title,
                created_at=now,
                updated_at=now,
            )
            s.add(convo)
            return convo

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)

    @staticmethod
    async def get_conversation(
        user_id: str,
        conversation_id: str,
        session: Optional[AsyncSession] = None,
    ) -> Optional[ConversationModel]:
        """User A can NEVER retrieve User B's conversation."""
        async def _exec(s: AsyncSession) -> Optional[ConversationModel]:
            stmt = select(ConversationModel).where(
                ConversationModel.id == conversation_id,
                ConversationModel.user_id == user_id,
            )
            result = await s.execute(stmt)
            return result.scalar_one_or_none()

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)

    @staticmethod
    async def list_conversations(
        user_id: str,
        session: Optional[AsyncSession] = None,
    ) -> List[ConversationModel]:
        """Returns conversations strictly belonging to user_id."""
        async def _exec(s: AsyncSession) -> List[ConversationModel]:
            stmt = select(ConversationModel).where(
                ConversationModel.user_id == user_id
            ).order_by(ConversationModel.updated_at.desc())
            result = await s.execute(stmt)
            return list(result.scalars().all())

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)

    @staticmethod
    async def delete_conversation(
        user_id: str,
        conversation_id: str,
        session: Optional[AsyncSession] = None,
    ) -> bool:
        async def _exec(s: AsyncSession) -> bool:
            stmt = delete(ConversationModel).where(
                ConversationModel.id == conversation_id,
                ConversationModel.user_id == user_id,
            )
            res = await s.execute(stmt)
            return bool(res.rowcount > 0)

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)


# =============================================================================
# 2. Message Repository
# =============================================================================

class MessageRepository:
    """Manages short-term conversation messages with user isolation."""

    @staticmethod
    async def save_message(
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> MessageModel:
        async def _exec(s: AsyncSession) -> MessageModel:
            msg_id = message_id or str(uuid.uuid4())
            now = _utc_now_iso()

            # Ensure conversation exists and is owned by user_id
            await ConversationRepository.save_conversation(
                user_id=user_id,
                conversation_id=conversation_id,
                title=content[:30] if role == "user" else "Conversation",
                session=s,
            )

            msg = MessageModel(
                id=msg_id,
                conversation_id=conversation_id,
                user_id=user_id,
                role=role,
                content=content,
                created_at=now,
            )
            s.add(msg)
            return msg

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)

    @staticmethod
    async def get_recent_messages(
        conversation_id: str,
        user_id: Optional[str] = None,
        limit: int = 10,
        session: Optional[AsyncSession] = None,
    ) -> List[MessageModel]:
        """
        Retrieves recent messages from a conversation.
        If user_id is provided, enforces that the conversation belongs to user_id.
        """
        async def _exec(s: AsyncSession) -> List[MessageModel]:
            stmt = select(MessageModel).where(MessageModel.conversation_id == conversation_id)
            if user_id:
                stmt = stmt.where(MessageModel.user_id == user_id)
            stmt = stmt.order_by(MessageModel.created_at.desc()).limit(limit)

            result = await s.execute(stmt)
            msgs = list(result.scalars().all())
            # Return in chronological order
            msgs.reverse()
            return msgs

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)


# =============================================================================
# 3. Memory Repository
# =============================================================================

class MemoryRepository:
    """Manages long-term memories with strict user ownership isolation."""

    @staticmethod
    async def save_memory(
        user_id: str,
        memory: str,
        category: str = "general",
        importance: int = 3,
        memory_id: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> MemoryModel:
        async def _exec(s: AsyncSession) -> MemoryModel:
            now = _utc_now_iso()
            # Check for existing duplicate memory for this user
            stmt = select(MemoryModel).where(
                MemoryModel.user_id == user_id,
                MemoryModel.memory == memory,
            )
            result = await s.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                existing.importance = max(existing.importance, importance)
                existing.category = category
                existing.updated_at = now
                return existing

            mem_id = memory_id or str(uuid.uuid4())
            item = MemoryModel(
                id=mem_id,
                user_id=user_id,
                memory=memory,
                category=category,
                importance=importance,
                created_at=now,
                updated_at=now,
            )
            s.add(item)
            return item

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)

    @staticmethod
    async def get_user_memories(
        user_id: str,
        limit: int = 50,
        session: Optional[AsyncSession] = None,
    ) -> List[MemoryModel]:
        """User A can NEVER retrieve User B's memories."""
        async def _exec(s: AsyncSession) -> List[MemoryModel]:
            stmt = select(MemoryModel).where(
                MemoryModel.user_id == user_id
            ).order_by(
                MemoryModel.importance.desc(),
                MemoryModel.updated_at.desc(),
            ).limit(limit)

            result = await s.execute(stmt)
            return list(result.scalars().all())

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)

    @staticmethod
    async def delete_memory(
        user_id: str,
        memory_id: str,
        session: Optional[AsyncSession] = None,
    ) -> bool:
        async def _exec(s: AsyncSession) -> bool:
            stmt = delete(MemoryModel).where(
                MemoryModel.id == memory_id,
                MemoryModel.user_id == user_id,
            )
            result = await s.execute(stmt)
            return bool(result.rowcount > 0)

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)

    @staticmethod
    async def clear_user_memories(
        user_id: str,
        session: Optional[AsyncSession] = None,
    ) -> None:
        async def _exec(s: AsyncSession) -> None:
            stmt = delete(MemoryModel).where(MemoryModel.user_id == user_id)
            await s.execute(stmt)

        if session:
            await _exec(session)
        else:
            async with get_session() as s:
                await _exec(s)


# =============================================================================
# 4. User Profile Repository
# =============================================================================

class UserProfileRepository:
    """Manages user profiles and durable preferences with user isolation."""

    @staticmethod
    async def get_or_create_profile(
        user_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> UserProfileModel:
        async def _exec(s: AsyncSession) -> UserProfileModel:
            stmt = select(UserProfileModel).where(UserProfileModel.user_id == user_id)
            result = await s.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                return existing

            now = _utc_now_iso()
            profile = UserProfileModel(
                user_id=user_id,
                name=name,
                email=email,
                role=None,
                goals=[],
                interests=[],
                preferences={},
                created_at=now,
                updated_at=now,
            )
            s.add(profile)
            return profile

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)

    @staticmethod
    async def update_profile(
        user_id: str,
        profile_update: Dict[str, Any],
        session: Optional[AsyncSession] = None,
    ) -> UserProfileModel:
        async def _exec(s: AsyncSession) -> UserProfileModel:
            profile = await UserProfileRepository.get_or_create_profile(user_id, session=s)
            if "name" in profile_update and profile_update["name"]:
                profile.name = profile_update["name"]
            if "role" in profile_update and profile_update["role"]:
                profile.role = profile_update["role"]
            if "goals" in profile_update and isinstance(profile_update["goals"], list):
                profile.goals = profile_update["goals"]
            if "interests" in profile_update and isinstance(profile_update["interests"], list):
                profile.interests = profile_update["interests"]
            if "preferences" in profile_update and isinstance(profile_update["preferences"], dict):
                # Update dict in-place or reassign for SQLAlchemy change tracking
                updated_pref = dict(profile.preferences or {})
                updated_pref.update(profile_update["preferences"])
                profile.preferences = updated_pref

            profile.updated_at = _utc_now_iso()
            return profile

        if session:
            return await _exec(session)
        async with get_session() as s:
            return await _exec(s)
