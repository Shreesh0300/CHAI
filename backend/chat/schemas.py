"""
Schemas and models for CHAI Conversational Layer and Intent Routing.
"""
from typing import List, Optional, Any, Dict, Literal
from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    """Structured decision output from the Intent Router."""
    intent: Literal["chat", "solve"]
    confidence: float = Field(..., ge=0.0, le=1.0, description="Routing confidence (0.0 to 1.0)")
    reason: str = Field(..., description="Deterministically logged explanation for the routing decision")


class ChatRequest(BaseModel):
    """Input payload for POST /api/chat."""
    message: str = Field(..., description="User message or query")
    conversation_id: Optional[str] = Field(None, description="Optional conversation thread ID")
    user_id: Optional[str] = Field(None, description="Optional authenticated user ID")
    session_id: Optional[str] = Field(None, description="Optional session token for guest users")
    # For backward compatibility if callers pass 'problem'
    problem: Optional[str] = Field(None, description="Alias for message")


class ChatResponse(BaseModel):
    """Unified response payload for POST /api/chat."""
    mode: Literal["chat", "solve"]
    conversation_id: str
    message: str
    intent_result: Optional[IntentResult] = None
    memories_used: List[str] = Field(default_factory=list)
    request_status: str = "completed"
    # Fields to maintain 100% compatibility with existing solve UI / consumers
    final_synthesized_answer: Optional[str] = None
    final_answer: Optional[str] = None
    agent_execution_statuses: List[Any] = Field(default_factory=list)
    retrieved_sources: List[str] = Field(default_factory=list)
    selected_agents: List[str] = Field(default_factory=list)
    execution_trace: List[Dict[str, Any]] = Field(default_factory=list)
