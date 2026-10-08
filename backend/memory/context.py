"""
Centralized Context and Memory Manager for CHAI.
Assembles short-term conversation history, relevant long-term memories,
and user profile data for both LangChain Chat Mode and LangGraph Solve Mode.
"""
from typing import List, Optional, Dict, Any
from backend.memory.models import (
    MemoryItem,
    UserProfile,
    ChatMessageRecord,
    ContextPayload,
)
from backend.memory.store import memory_store, is_guest_user
from backend.memory.retrieval import memory_retriever
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class ContextManager:
    """
    Coordinates context retrieval and formatting across all 3 memory levels:
    - Level A: Recent chat history in current conversation
    - Level B: Long-term durable memories filtered by relevance
    - Level C: User profile & personal preferences
    """

    async def get_recent_messages(
        self,
        conversation_id: str,
        user_id: Optional[str] = None,
        limit: int = 6,
    ) -> List[ChatMessageRecord]:
        """Fetches the most recent conversation messages (Level A)."""
        if not conversation_id:
            return []
        return await memory_store.get_recent_messages(
            conversation_id=conversation_id,
            user_id=user_id,
            limit=limit,
        )

    async def get_relevant_memories(
        self,
        user_id: str,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[MemoryItem]:
        """Fetches and relevance-filters long-term memories (Level B)."""
        all_memories = await memory_store.get_user_memories(
            user_id=user_id,
            session_id=session_id,
            limit=50,
        )
        return memory_retriever.retrieve(query=query, memories=all_memories, limit=limit)

    async def get_user_profile(self, user_id: str) -> UserProfile:
        """Fetches user profile and preferences (Level C)."""
        return await memory_store.get_or_create_profile(user_id=user_id)

    async def build_chat_context(
        self,
        user_id: str,
        query: str,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> ContextPayload:
        """
        Builds the complete context payload for LangChain Chat Mode.
        """
        profile = await self.get_user_profile(user_id)
        recent = (
            await self.get_recent_messages(conversation_id, user_id=user_id, limit=6)
            if conversation_id
            else []
        )
        relevant_memories = await self.get_relevant_memories(
            user_id=user_id,
            query=query,
            session_id=session_id,
            limit=4,
        )

        # Build context lines
        lines: List[str] = []
        if profile.name and not is_guest_user(user_id):
            lines.append(f"- User Name: {profile.name}")
        if profile.role:
            lines.append(f"- Role: {profile.role}")
        if profile.preferences:
            pref_str = ", ".join(f"{k}: {v}" for k, v in profile.preferences.items())
            lines.append(f"- User Preferences: {pref_str}")

        if relevant_memories:
            lines.append("- Relevant User Knowledge:")
            for m in relevant_memories:
                lines.append(f"  * {m.memory}")

        formatted = "\n".join(lines)

        return ContextPayload(
            user_id=user_id,
            conversation_id=conversation_id,
            user_profile=profile,
            recent_messages=recent,
            relevant_memories=relevant_memories,
            formatted_context_string=formatted,
        )

    async def build_solve_context(
        self,
        user_id: str,
        problem: str,
        conversation_id: Optional[str] = None,
        existing_context: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Constructs an enriched, structured context string for LangGraph Solve Mode.
        Passed cleanly into SolveRequest.context without disrupting agent signatures.
        """
        profile = await self.get_user_profile(user_id)
        relevant_memories = await self.get_relevant_memories(
            user_id=user_id,
            query=problem,
            session_id=session_id,
            limit=4,
        )
        recent_messages = (
            await self.get_recent_messages(conversation_id, user_id=user_id, limit=4)
            if conversation_id
            else []
        )

        sections: List[str] = []

        # 1. Existing caller-supplied domain context
        if existing_context and existing_context.strip():
            sections.append(f"[ENVIRONMENT / DOMAIN CONTEXT]\n{existing_context.strip()}")

        # 2. Known User Context (Memories & Profile)
        user_facts: List[str] = []
        if profile.name and not is_guest_user(user_id):
            user_facts.append(f"- Name: {profile.name}")
        if profile.role:
            user_facts.append(f"- Role: {profile.role}")
        if profile.preferences:
            pref_summary = ", ".join(f"{k}: {v}" for k, v in profile.preferences.items())
            user_facts.append(f"- Preferences: {pref_summary}")

        for m in relevant_memories:
            user_facts.append(f"- {m.memory}")

        if user_facts:
            sections.append(
                "[KNOWN USER CONTEXT (Background goals & preferences - use as context, not absolute truth)]\n"
                + "\n".join(user_facts)
            )

        # 3. Relevant Recent Conversation Snippet
        if recent_messages:
            convo_lines = [f"{msg.role.upper()}: {msg.content}" for msg in recent_messages[-3:]]
            sections.append("[RECENT RELEVANT CONVERSATION]\n" + "\n".join(convo_lines))

        enriched = "\n\n".join(sections)
        logger.debug(f"[CONTEXT MANAGER] Enriched solve context ({len(enriched)} chars) generated for user {user_id}")
        return enriched


# Global singleton instance
context_manager = ContextManager()
