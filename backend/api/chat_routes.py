"""
FastAPI Routes for CHAI Conversational Layer and Memory.
Provides unified entry point POST /api/chat that automatically routes
between LangChain Chat Mode and LangGraph Solve Mode, while enriching
the solve pipeline with personalized user context.
"""
import time
import uuid
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Header, BackgroundTasks, Request
from fastapi.responses import StreamingResponse

from backend.chat.schemas import ChatRequest, ChatResponse, IntentResult
from backend.chat.router import intent_router
from backend.chat.service import chat_service
from backend.core.coordinator import CHAICoordinator
from backend.core.schemas import SolveRequest
from backend.core.execution_events import execution_event_manager
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
    uid = (request.user_id or x_user_id or "").strip()
    sid = (request.session_id or "").strip()
    if uid and not uid.startswith("guest") and uid != "guest_session":
        return uid
    if sid:
        return f"guest_{sid}"
    if uid:
        return uid
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

    req_id = getattr(req, "request_id", None) or str(uuid.uuid4())
    req.request_id = req_id
    execution_event_manager.create_session(req_id)

    user_id = _resolve_user_id(req, x_user_id)
    conversation_id = req.conversation_id or str(uuid.uuid4())
    session_id = req.session_id

    # Retrieve recent conversation messages for context-aware routing
    recent_msgs = await memory_store.get_recent_messages(
        conversation_id=conversation_id,
        user_id=user_id,
        limit=6,
    )
    context_preview = "\n".join(f"{m.role}: {m.content}" for m in recent_msgs) if recent_msgs else None

    from backend.db.repositories import ConversationRepository
    from backend.chat.title_service import title_service

    # Check if conversation already has an intelligent title
    existing_convo = await ConversationRepository.get_conversation_with_messages(
        user_id=user_id,
        conversation_id=conversation_id,
    )
    existing_title = existing_convo.get("title") if existing_convo else None
    def _is_meaningful_title(t: Optional[str]) -> bool:
        if not t or t in ("New Conversation", "Conversation", "New chat", ""):
            return False
        if t.endswith("...") or t.endswith("…"):
            return False
        lower_t = t.strip().lower()
        if lower_t.endswith((" of", " to", " for", " in", " on", " with", " at", " by", " and", " or", " the", " a")):
            return False
        if lower_t.startswith((
            "im thinking", "i'm thinking", "i am thinking", "thinking to", "thinking of", "thinking about",
            "can you tell", "could you", "what is the", "trying to", "planning to",
        )):
            return False
        return True

    has_meaningful_title = _is_meaningful_title(existing_title)

    # Launch AI title generation concurrently if needed (non-blocking)
    title_task: Optional[asyncio.Task] = None
    if not has_meaningful_title:
        title_task = asyncio.create_task(
            title_service.generate_title(message_text, context=context_preview)
        )

    async def _resolve_title() -> str:
        nonlocal title_task, existing_title, message_text
        if title_task:
            try:
                ai_title = await asyncio.wait_for(title_task, timeout=8.0)
                if _is_meaningful_title(ai_title):
                    return ai_title
            except Exception:
                pass
        if _is_meaningful_title(existing_title):
            return existing_title
        return title_service.generate_fallback_title(message_text)

    # 1. Intent Classification
    if getattr(req, "mode", None) in ("solve", "research", "agent"):
        intent_result = IntentResult(
            intent="solve",
            confidence=1.0,
            reason=f"Client explicitly requested mode '{req.mode}'.",
        )
    elif getattr(req, "mode", None) == "chat":
        intent_result = IntentResult(
            intent="chat",
            confidence=1.0,
            reason="Client explicitly requested mode 'chat'.",
        )
    else:
        intent_result: IntentResult = await intent_router.classify(message_text, context=context_preview)

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
        await execution_event_manager.emit(
            request_id=req_id,
            event="chat_mode_selected",
            status="running",
            message="CHAI is responding...",
        )
        try:
            # Generate personalized reply with recent history & relevant memories
            reply_text, memories_used = await chat_service.generate_reply(
                message=message_text,
                user_id=user_id,
                conversation_id=conversation_id,
                session_id=session_id,
                request_id=req_id,
            )

            from backend.core.domain_lenses import normalize_domain, canonicalize_domain
            from backend.core.router import resolve_domain

            explicit_category = (getattr(req, "category", None) or "AUTO").strip().upper()
            chat_domain_cat, _ = resolve_domain(
                problem=message_text,
                category=explicit_category,
                context=context_preview,
            )
            chat_resolved_dom = canonicalize_domain(chat_domain_cat, default="business")

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
                extra_data={
                    "resolved_domain": chat_resolved_dom,
                    "domain": chat_resolved_dom,
                    "request_id": req_id,
                },
            )

            # Launch asynchronous memory extraction (non-blocking)
            background_tasks.add_task(
                memory_extractor.extract_and_store,
                user_id=user_id,
                user_message=message_text,
                assistant_reply=reply_text,
                session_id=session_id,
            )

            # Resolve AI-generated conversation title
            convo_title = await _resolve_title()
            await ConversationRepository.save_conversation(
                user_id=user_id,
                conversation_id=conversation_id,
                title=convo_title,
                is_final_title=True,
            )

            await execution_event_manager.emit(
                request_id=req_id,
                event="conversation_title",
                title=convo_title,
            )

            await execution_event_manager.emit(
                request_id=req_id,
                event="final_answer",
                status="completed",
                final_answer=reply_text,
                message="Response delivered",
            )

            return ChatResponse(
                request_id=req_id,
                mode="chat",
                conversation_id=conversation_id,
                title=convo_title,
                message=reply_text,
                intent_result=intent_result,
                memories_used=memories_used,
                request_status="completed",
                domain_category=chat_domain_cat,
                resolved_domain=chat_resolved_dom,
                final_synthesized_answer=reply_text,
                final_answer=reply_text,
            )

        except Exception as exc:
            from backend.core.execution_events import RequestCancelledException
            if isinstance(exc, (RequestCancelledException, asyncio.CancelledError)) or execution_event_manager.is_cancelled(req_id):
                cancel_msg = "Generation cancelled by user."
                try:
                    await memory_store.add_message(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        role="user",
                        content=message_text,
                    )
                except Exception:
                    pass
                convo_title = existing_title or title_service.generate_fallback_title(message_text)
                return ChatResponse(
                    request_id=req_id,
                    mode="chat",
                    conversation_id=conversation_id,
                    title=convo_title,
                    message=cancel_msg,
                    intent_result=intent_result,
                    memories_used=[],
                    request_status="cancelled",
                    final_synthesized_answer=cancel_msg,
                    final_answer=cancel_msg,
                )
            logger.error(f"[CHAT ENDPOINT] Error in chat mode: {exc}")
            await execution_event_manager.emit(
                request_id=req_id,
                event="request_failed",
                status="failed",
                error=str(exc),
                message="Chat generation failed",
            )
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

            # Pass enriched context and domain category into existing coordinator
            # Note: conversation_id is handled below by chat_routes to avoid duplicate writes
            solve_req = SolveRequest(
                request_id=req_id,
                problem=message_text,
                user_id=user_id,
                context=enriched_context,
                conversation_id=None,
                session_id=session_id,
                category=getattr(req, "category", None),
            )

            solve_res = await coordinator.process_request(solve_req)

            final_answer_text = (
                solve_res.final_synthesized_answer
                or solve_res.final_answer
                or "Multi-agent reasoning completed."
            )

            from backend.core.domain_lenses import canonicalize_domain
            raw_res_dom = getattr(solve_res, "resolved_domain", None) or getattr(solve_res, "domain_category", None)
            canonical_solve_dom = canonicalize_domain(raw_res_dom, default="business")

            # Store short-term conversation messages (Level A)
            await memory_store.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=message_text,
            )
            if solve_res.request_status != "cancelled":
                await memory_store.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="assistant",
                    content=final_answer_text,
                    extra_data={
                        "resolved_domain": canonical_solve_dom,
                        "domain": canonical_solve_dom,
                        "selected_agents": solve_res.selected_agents or [],
                        "request_id": req_id,
                    },
                )

                # Launch asynchronous memory extraction (non-blocking)
                background_tasks.add_task(
                    memory_extractor.extract_and_store,
                    user_id=user_id,
                    user_message=message_text,
                    assistant_reply=final_answer_text,
                    session_id=session_id,
                )


            # Resolve AI-generated conversation title
            convo_title = await _resolve_title()
            await ConversationRepository.save_conversation(
                user_id=user_id,
                conversation_id=conversation_id,
                title=convo_title,
                is_final_title=True,
            )

            await execution_event_manager.emit(
                request_id=req_id,
                event="conversation_title",
                title=convo_title,
            )

            return ChatResponse(
                request_id=req_id,
                mode="solve",
                conversation_id=conversation_id,
                title=convo_title,
                message=final_answer_text,
                intent_result=intent_result,
                memories_used=memories_used,
                request_status=solve_res.request_status or "completed",
                domain_category=getattr(solve_res, "domain_category", None) or canonical_solve_dom,
                resolved_domain=canonical_solve_dom,
                final_synthesized_answer=solve_res.final_synthesized_answer,
                final_answer=solve_res.final_answer,
                agent_execution_statuses=solve_res.agent_execution_statuses,
                retrieved_sources=solve_res.retrieved_sources,
                selected_agents=solve_res.selected_agents,
                execution_trace=solve_res.execution_trace,
            )

        except Exception as exc:
            from backend.core.execution_events import RequestCancelledException
            if isinstance(exc, (RequestCancelledException, asyncio.CancelledError)) or execution_event_manager.is_cancelled(req_id):
                cancel_msg = "Generation cancelled by user."
                try:
                    await memory_store.add_message(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        role="user",
                        content=message_text,
                    )
                except Exception:
                    pass
                convo_title = existing_title or title_service.generate_fallback_title(message_text)
                return ChatResponse(
                    request_id=req_id,
                    mode="solve",
                    conversation_id=conversation_id,
                    title=convo_title,
                    message=cancel_msg,
                    intent_result=intent_result,
                    memories_used=memories_used if "memories_used" in locals() else [],
                    request_status="cancelled",
                    final_synthesized_answer=cancel_msg,
                    final_answer=cancel_msg,
                )
            logger.error(f"[CHAT ENDPOINT] Error in solve mode: {exc}")
            await execution_event_manager.emit(
                request_id=req_id,
                event="request_failed",
                status="failed",
                error=str(exc),
                message="Solve execution failed",
            )
            raise HTTPException(status_code=500, detail=f"Solve error: {str(exc)}")


@router.post("/chat/{request_id}/pause")
async def pause_chat(request_id: str):
    """Pauses generation for an active chat/solve request."""
    if not execution_event_manager.has_session(request_id):
        raise HTTPException(status_code=404, detail=f"Execution request '{request_id}' not found")
    res = await execution_event_manager.pause_request(request_id)
    return {"request_id": request_id, "status": "paused", "success": res}


@router.post("/chat/{request_id}/resume")
async def resume_chat(request_id: str):
    """Resumes generation for a paused chat/solve request."""
    if not execution_event_manager.has_session(request_id):
        raise HTTPException(status_code=404, detail=f"Execution request '{request_id}' not found")
    res = await execution_event_manager.resume_request(request_id)
    return {"request_id": request_id, "status": "resumed", "success": res}


@router.post("/chat/{request_id}/cancel")
async def cancel_chat(request_id: str):
    """Cancels generation for an active chat/solve request."""
    if not execution_event_manager.has_session(request_id):
        raise HTTPException(status_code=404, detail=f"Execution request '{request_id}' not found")
    res = await execution_event_manager.cancel_request(request_id)
    return {"request_id": request_id, "status": "cancelled", "success": res}


@router.get("/chat/{request_id}/events")
async def get_chat_events(request_id: str, request: Request):
    """
    Server-Sent Events endpoint streaming live agent execution events for /chat requests.
    """
    start_wait = time.time()
    while not execution_event_manager.has_session(request_id):
        if time.time() - start_wait > 3.0:
            raise HTTPException(status_code=404, detail=f"Execution request '{request_id}' not found")
        await asyncio.sleep(0.05)

    async def event_generator():
        try:
            async for event in execution_event_manager.subscribe(request_id, wait_for_init_seconds=0.1):
                if await request.is_disconnected():
                    break
                yield f"data: {event.model_dump_json()}\n\n"
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"SSE chat event stream ended for {request_id}: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
