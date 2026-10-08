"""
SQLAlchemy ORM Models for CHAI durable PostgreSQL storage.
Defines tables for conversations, messages, long-term memories, and user profiles.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationModel(Base):
    """
    Durable conversation thread metadata.
    """
    __tablename__ = "conversations"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(128), index=True, nullable=False)
    title = Column(String(255), nullable=False, default="New Conversation")
    created_at = Column(String(64), nullable=False, default=_utc_now_iso)
    updated_at = Column(String(64), nullable=False, default=_utc_now_iso)


class MessageModel(Base):
    """
    Individual message in short-term conversation memory.
    """
    __tablename__ = "messages"

    id = Column(String(64), primary_key=True)
    conversation_id = Column(String(64), index=True, nullable=False)
    user_id = Column(String(128), index=True, nullable=False)
    role = Column(String(32), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    created_at = Column(String(64), nullable=False, default=_utc_now_iso)


class MemoryModel(Base):
    """
    Durable, future-useful user memory fact.
    """
    __tablename__ = "memories"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(128), index=True, nullable=False)
    memory = Column(Text, nullable=False)
    category = Column(String(64), nullable=False, default="general")
    importance = Column(Integer, nullable=False, default=3)
    created_at = Column(String(64), nullable=False, default=_utc_now_iso)
    updated_at = Column(String(64), nullable=False, default=_utc_now_iso)


class UserProfileModel(Base):
    """
    Structured profile and durable preferences for an authenticated user.
    """
    __tablename__ = "user_profiles"

    user_id = Column(String(128), primary_key=True)
    name = Column(String(128), nullable=True)
    email = Column(String(128), nullable=True)
    role = Column(String(128), nullable=True)
    goals = Column(JSON, nullable=False, default=list)
    interests = Column(JSON, nullable=False, default=list)
    preferences = Column(JSON, nullable=False, default=dict)
    created_at = Column(String(64), nullable=False, default=_utc_now_iso)
    updated_at = Column(String(64), nullable=False, default=_utc_now_iso)
