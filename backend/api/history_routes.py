import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class HistoryMessage(BaseModel):
    id: str
    role: str
    content: str
    attachments: Optional[List[str]] = None

class ConversationItem(BaseModel):
    id: str
    title: str
    mode: str
    layout: str
    updated: str
    messages: List[HistoryMessage] = []

# In-memory storage for conversation history
_history_db: Dict[str, ConversationItem] = {
    "sample-1": ConversationItem(
        id="sample-1",
        title="Market research & competitive analysis",
        mode="research",
        layout="workspace",
        updated="12m ago",
        messages=[
            HistoryMessage(id="m1", role="user", content="Analyze the enterprise AI agent market landscape."),
            HistoryMessage(id="m2", role="assistant", content="The enterprise AI market is transitioning from single-model chat interfaces to multi-agent architectures that orchestrate specialized agents for research, execution, evaluation, and security.")
        ]
    ),
    "sample-2": ConversationItem(
        id="sample-2",
        title="Security audit & compliance check",
        mode="agent",
        layout="workspace",
        updated="2h ago",
        messages=[
            HistoryMessage(id="m3", role="user", content="Run a security verification on our auth payload structure."),
            HistoryMessage(id="m4", role="assistant", content="Guardian agent reviewed the endpoint protections: zero plaintext leaks detected, session tokens sanitized.")
        ]
    )
}

@router.get("", response_model=List[ConversationItem])
async def list_conversations():
    return list(_history_db.values())

@router.post("", response_model=ConversationItem)
async def save_conversation(item: ConversationItem):
    _history_db[item.id] = item
    return item

@router.get("/{conversation_id}", response_model=ConversationItem)
async def get_conversation(conversation_id: str):
    item = _history_db.get(conversation_id)
    if not item:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return item

@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    if conversation_id in _history_db:
        del _history_db[conversation_id]
    return {"success": True}
