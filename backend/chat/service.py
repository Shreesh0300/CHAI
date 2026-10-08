"""
LangChain Conversational Service for CHAI Chat Mode.
Uses LangChain for prompt composition, message history formatting,
context injection, and model invocation.
"""
import os
import asyncio
from typing import List, Optional, Tuple, Any
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.output_parsers import StrOutputParser

from backend.chat.prompts import create_chat_prompt_template
from backend.memory.context import context_manager
from backend.memory.models import ChatMessageRecord, MemoryItem
from backend.shared.llm_client import (
    get_gemini_api_key,
    get_default_gemini_model,
    classify_gemini_error,
)
from backend.shared.logger import get_logger

logger = get_logger(__name__)


def _build_langchain_messages(records: List[ChatMessageRecord]) -> List[BaseMessage]:
    """Converts internal short-term chat records into LangChain message objects."""
    messages: List[BaseMessage] = []
    for r in records:
        if r.role == "user":
            messages.append(HumanMessage(content=r.content))
        elif r.role == "assistant":
            messages.append(AIMessage(content=r.content))
    return messages


class LangChainChatService:
    """
    Handles conversational interactions in CHAI Chat Mode using LangChain.
    Fast, context-aware, personalized, and single-turn without triggering 12 agents.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or get_default_gemini_model()
        self.prompt_template = create_chat_prompt_template()

    def _get_chat_model(self) -> Any:
        """Initializes or retrieves the configured ChatGoogleGenerativeAI instance."""
        api_key = get_gemini_api_key()
        is_mock = os.getenv("CHAI_MOCK_MODE", "").lower() in ("true", "1", "yes") or not api_key

        if is_mock:
            # Safe mock runnable for local testing without active API key
            from langchain_core.runnables import RunnableLambda
            def mock_reply(messages: Any) -> str:
                return "Hello! I am CHAI in conversational mode. How can I help you today?"
            return RunnableLambda(mock_reply)

        from langchain_google_genai import ChatGoogleGenerativeAI
        effective_model = self.model_name or get_default_gemini_model()
        return ChatGoogleGenerativeAI(
            model=effective_model,
            temperature=0.3,
            api_key=api_key,
            timeout=30.0,
        )

    def build_chain(self) -> Any:
        """Constructs the LCEL chain: prompt_template | chat_model | StrOutputParser."""
        chat_model = self._get_chat_model()
        return self.prompt_template | chat_model | StrOutputParser()

    async def generate_reply(
        self,
        message: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[str, List[str]]:
        """
        Executes LangChain chat generation with context injection and history.
        Returns: (assistant_reply_text, list_of_memory_summaries_used)
        """
        # 1. Retrieve Level A, B, and C context via ContextManager
        context_payload = await context_manager.build_chat_context(
            user_id=user_id,
            query=message,
            conversation_id=conversation_id,
            session_id=session_id,
        )

        user_context_block = ""
        if context_payload.formatted_context_string.strip():
            user_context_block = f"\n[USER CONTEXT & MEMORIES]\n{context_payload.formatted_context_string}\n"

        # 2. Convert recent history records to LangChain messages
        history_messages = _build_langchain_messages(context_payload.recent_messages)

        # 3. Build LangChain runnable chain: prompt | model | parser
        chain = self.build_chain()

        # Observability: Safe debug logging for inspection
        from backend.chat.prompts import SYSTEM_CHAT_PROMPT
        from backend.memory.store import sanitize_sensitive_data

        history_repr_lines = []
        for msg in history_messages:
            prefix = "Human" if isinstance(msg, HumanMessage) else "AI"
            history_repr_lines.append(f"{prefix}: {sanitize_sensitive_data(str(msg.content))}")
        history_repr = "\n".join(history_repr_lines) if history_repr_lines else "(No previous history)"

        safe_context = sanitize_sensitive_data(user_context_block.strip() or "(None)")
        safe_input = sanitize_sensitive_data(message)

        debug_banner = (
            "\n================ LANGCHAIN CHAT DEBUG ================\n"
            "MODE: CHAT\n\n"
            f"SYSTEM PROMPT:\n{SYSTEM_CHAT_PROMPT.strip()}\n\n"
            f"MESSAGE HISTORY:\n{history_repr}\n\n"
            f"USER CONTEXT:\n{safe_context}\n\n"
            f"FINAL LANGCHAIN INPUT:\n{safe_input}\n"
            "=================================================="
        )
        logger.info(debug_banner)

        # 4. Invoke model asynchronously
        try:
            logger.info(f"[CHAT SERVICE] Generating LangChain reply for user {user_id}...")
            response = await chain.ainvoke({
                "user_context_block": user_context_block,
                "history": history_messages,
                "input": message,
            })
            reply_text = str(response).strip()
        except Exception as exc:
            err_cat, err_msg = classify_gemini_error(exc)
            effective_model = self.model_name or get_default_gemini_model()
            api_key = get_gemini_api_key()
            if (err_cat in ("[QUOTA_ERROR]", "[NOT_FOUND_ERROR]", "[API_ERROR]") or "404" in str(exc) or "not available" in str(exc).lower()) and effective_model != "gemini-flash-lite-latest" and api_key:
                logger.warning(f"[CHAT SERVICE] Primary model '{effective_model}' failed ({err_cat}). Falling back to gemini-flash-lite-latest...")
                try:
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    fallback_model = ChatGoogleGenerativeAI(
                        model="gemini-flash-lite-latest",
                        temperature=0.3,
                        api_key=api_key,
                        timeout=30.0,
                    )
                    fallback_chain = self.prompt_template | fallback_model | StrOutputParser()
                    response = await fallback_chain.ainvoke({
                        "user_context_block": user_context_block,
                        "history": history_messages,
                        "input": message,
                    })
                    reply_text = str(response).strip()
                except Exception as fb_exc:
                    fb_cat, fb_msg = classify_gemini_error(fb_exc)
                    logger.error(f"[CHAT SERVICE] Fallback execution error: {fb_cat} {fb_msg}")
                    reply_text = f"I encountered a temporary issue connecting to my reasoning engine: {fb_msg}"
            else:
                logger.error(f"[CHAT SERVICE] LangChain execution error: {err_cat} {err_msg}")
                reply_text = f"I encountered a temporary issue connecting to my reasoning engine: {err_msg}"

        memories_used = [m.memory for m in context_payload.relevant_memories]
        return reply_text, memories_used


# Global singleton instance
chat_service = LangChainChatService()
