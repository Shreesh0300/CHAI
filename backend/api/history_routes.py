import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field

from backend.db.repositories import ConversationRepository, MessageRepository
from backend.shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _resolve_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
) -> str:
    """Extracts user identity or defaults to isolated guest session."""
    uid = (user_id or x_user_id or "").strip()
    sid = (session_id or x_session_id or "").strip()
    if uid and not uid.startswith("guest") and uid != "guest_session":
        return uid
    if sid:
        return f"guest_{sid}"
    if uid:
        return uid
    return "guest_default"


class HistoryMessage(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    resolved_domain: Optional[str] = None
    domain: Optional[str] = None
    selected_agents: List[str] = Field(default_factory=list)
    request_id: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    preview: Optional[str] = None


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[HistoryMessage] = Field(default_factory=list)


class UpdateConversationRequest(BaseModel):
    title: str


@router.get("", response_model=List[ConversationSummary])
async def list_conversations(
    search: Optional[str] = Query(None, description="Search term matching title or content"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
):
    """
    Lists conversations owned strictly by the current user or guest session.
    Ordered by most recently updated.
    Supports case-insensitive search by title or message content.
    """
    effective_user_id = _resolve_user_id(x_user_id, x_session_id, user_id, session_id)
    convos = await ConversationRepository.list_conversations(
        user_id=effective_user_id,
        search=search,
        limit=limit,
        offset=offset,
    )

    summaries: List[ConversationSummary] = []
    for c in convos:
        # Get latest message for preview and count
        msgs = await MessageRepository.get_recent_messages(
            conversation_id=c.id,
            user_id=effective_user_id,
            limit=5,
        )
        preview_text = msgs[-1].content if msgs else ""
        if len(preview_text) > 80:
            preview_text = preview_text[:80].rsplit(" ", 1)[0] + "..."

        summaries.append(
            ConversationSummary(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=len(msgs),
                preview=preview_text,
            )
        )

    return summaries


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
):
    """
    Retrieves full conversation details and ordered messages.
    Enforces strict user isolation: returns 404 if not owned by user.
    """
    effective_user_id = _resolve_user_id(x_user_id, x_session_id, user_id, session_id)
    data = await ConversationRepository.get_conversation_with_messages(
        user_id=effective_user_id,
        conversation_id=conversation_id,
    )
    if not data:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages: List[HistoryMessage] = []
    for m in data["messages"]:
        extra = getattr(m, "extra_data", {}) or {}
        messages.append(
            HistoryMessage(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                resolved_domain=extra.get("resolved_domain"),
                domain=extra.get("domain"),
                selected_agents=extra.get("selected_agents", []),
                request_id=extra.get("request_id"),
                extra_data=extra,
            )
        )

    return ConversationDetail(
        id=data["id"],
        title=data["title"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        messages=messages,
    )


@router.patch("/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(
    conversation_id: str,
    body: UpdateConversationRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
):
    """Updates conversation title."""
    effective_user_id = _resolve_user_id(x_user_id, x_session_id, user_id, session_id)
    convo = await ConversationRepository.update_title(
        user_id=effective_user_id,
        conversation_id=conversation_id,
        title=body.title,
    )
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationSummary(
        id=convo.id,
        title=convo.title,
        created_at=convo.created_at,
        updated_at=convo.updated_at,
    )


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
):
    """Deletes conversation and associated messages."""
    effective_user_id = _resolve_user_id(x_user_id, x_session_id, user_id, session_id)
    success = await ConversationRepository.delete_conversation(
        user_id=effective_user_id,
        conversation_id=conversation_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "deleted_id": conversation_id}
