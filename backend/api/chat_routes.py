"""
FastAPI Routes for CHAI Conversational Layer and Memory.
Provides unified entry point POST /api/chat that automatically routes
between LangChain Chat Mode and LangGraph Solve Mode, while enriching
the solve pipeline with personalized user context.
"""
import uuid
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Header, BackgroundTasks

from backend.chat.schemas import ChatRequest, ChatResponse, IntentResult
from backend.chat.router import intent_router
from backend.chat.service import chat_service
from backend.core.coordinator import CHAICoordinator
from backend.core.schemas import SolveRequest
from backend.memory.store import memory_store, is_guest_user
from backend.memory.context import context_manager
from backend.memory.extraction import memory_extractor
from backend.memory.models import MemoryItem, UserProfile
from backend.shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()
coordinator = CHAICoordinator()


def _resolve_user_id(request: ChatRequest, x_user_id: Optional[str] = None) -> str:
    """Determines user identity or defaults to isolated guest session."""
    if request.user_id and request.user_id.strip():
        return request.user_id.strip()
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    # Default to session or ephemeral guest ID
    if request.session_id and request.session_id.strip():
        return f"guest_{request.session_id.strip()}"
    return "guest_default"


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
):
    """
    Unified entry point for CHAI:
    Automatically determines whether the query requires:
    - CHAT: LangChain conversational assistant
    - SOLVE: 12-stage multi-agent LangGraph workflow
    """
    message_text = req.message or req.problem or ""
    if not message_text.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    user_id = _resolve_user_id(req, x_user_id)
    conversation_id = req.conversation_id or str(uuid.uuid4())
    session_id = req.session_id

    # 1. Intent Classification
    intent_result: IntentResult = await intent_router.classify(message_text)

    # Observability debug logging
    logger.info("================ INTENT ROUTER ================")
    logger.info(f"intent: {intent_result.intent.upper()}")
    logger.info(f"confidence: {intent_result.confidence:.2f}")
    logger.info(f"reason: {intent_result.reason}")

    # =========================================================================
    # CHAT MODE (LangChain)
    # =========================================================================
    if intent_result.intent == "chat":
        logger.info("================ CHAT MODE (LangChain) ================")
        try:
            # Generate personalized reply with recent history & relevant memories
            reply_text, memories_used = await chat_service.generate_reply(
                message=message_text,
                user_id=user_id,
                conversation_id=conversation_id,
                session_id=session_id,
            )

            # Store short-term conversation messages (Level A)
            await memory_store.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=message_text,
            )
            await memory_store.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=reply_text,
            )

            # Launch asynchronous memory extraction (non-blocking)
            background_tasks.add_task(
                memory_extractor.extract_and_store,
                user_id=user_id,
                user_message=message_text,
                assistant_reply=reply_text,
                session_id=session_id,
            )

            return ChatResponse(
                mode="chat",
                conversation_id=conversation_id,
                message=reply_text,
                intent_result=intent_result,
                memories_used=memories_used,
                request_status="completed",
                final_synthesized_answer=reply_text,
                final_answer=reply_text,
            )

        except Exception as exc:
            logger.error(f"[CHAT ENDPOINT] Error in chat mode: {exc}")
            raise HTTPException(status_code=500, detail=f"Chat error: {str(exc)}")

    # =========================================================================
    # SOLVE MODE (LangGraph)
    # =========================================================================
    else:
        logger.info("================ SOLVE MODE (LangGraph 12-Stage) ================")
        try:
            # Retrieve relevant memories and build enriched solve context
            enriched_context = await context_manager.build_solve_context(
                user_id=user_id,
                problem=message_text,
                conversation_id=conversation_id,
                session_id=session_id,
            )

            relevant_memories = await context_manager.get_relevant_memories(
                user_id=user_id,
                query=message_text,
                session_id=session_id,
                limit=4,
            )
            memories_used = [m.memory for m in relevant_memories]

            logger.info("================ SOLVE CONTEXT ================")
            logger.info(f"Enriched Context Length: {len(enriched_context)} characters")
            logger.info(f"Memories Injected: {len(memories_used)}")

            # Pass enriched context into existing coordinator
            solve_req = SolveRequest(
                problem=message_text,
                user_id=user_id,
                context=enriched_context,
            )

            solve_res = await coordinator.process_request(solve_req)

            final_answer_text = (
                solve_res.final_synthesized_answer
                or solve_res.final_answer
                or "Multi-agent reasoning completed."
            )

            # Store short-term conversation messages (Level A)
            await memory_store.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=message_text,
            )
            await memory_store.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=final_answer_text,
            )

            # Launch asynchronous memory extraction (non-blocking)
            background_tasks.add_task(
                memory_extractor.extract_and_store,
                user_id=user_id,
                user_message=message_text,
                assistant_reply=final_answer_text,
                session_id=session_id,
            )

            return ChatResponse(
                mode="solve",
                conversation_id=conversation_id,
                message=final_answer_text,
                intent_result=intent_result,
                memories_used=memories_used,
                request_status=solve_res.request_status or "completed",
                final_synthesized_answer=solve_res.final_synthesized_answer,
                final_answer=solve_res.final_answer,
                agent_execution_statuses=solve_res.agent_execution_statuses,
                retrieved_sources=solve_res.retrieved_sources,
                selected_agents=solve_res.selected_agents,
                execution_trace=solve_res.execution_trace,
            )

        except Exception as exc:
            logger.error(f"[CHAT ENDPOINT] Error in solve mode: {exc}")
            raise HTTPException(status_code=500, detail=f"Solve error: {str(exc)}")


# =============================================================================
# Memory Transparency & Management Endpoints
# =============================================================================

@router.get("/memories", response_model=List[MemoryItem])
async def list_memories(
    user_id: str = Query(..., description="User ID to retrieve memories for"),
    session_id: Optional[str] = Query(None),
):
    """Retrieves stored memories strictly for the specified user."""
    return await memory_store.get_user_memories(user_id=user_id, session_id=session_id)


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    user_id: str = Query(..., description="User ID requesting deletion"),
):
    """Deletes a memory item belonging to the specified user."""
    success = await memory_store.delete_memory(user_id=user_id, memory_id=memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or unauthorized.")
    return {"success": True, "deleted_id": memory_id}


@router.get("/profile", response_model=UserProfile)
async def get_profile(user_id: str = Query(...)):
    """Retrieves user profile and preferences."""
    return await memory_store.get_or_create_profile(user_id=user_id)


@router.post("/profile", response_model=UserProfile)
async def update_profile(user_id: str = Query(...), update_data: Dict[str, Any] = None):
    """Updates user profile or preferences."""
    return await memory_store.update_profile(user_id=user_id, profile_update=update_data or {})
