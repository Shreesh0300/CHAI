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
    # Optional mode override ('chat', 'solve', 'ask', 'research', 'agent')
    mode: Optional[str] = Field(None, description="Optional explicit mode requested by client")
    # Unique execution request ID for live event tracking
    request_id: Optional[str] = Field(None, description="Unique execution request ID for live event tracking")
    # Domain-Aware Reasoning: explicit user selection from the UI
    category: Optional[str] = Field(
        None,
        description="Explicit domain lens: 'AUTO', 'BUSINESS', 'PERSONAL', or 'SOFTWARE'. "
                    "None behaves as AUTO.",
    )


class ChatResponse(BaseModel):
    """Unified response payload for POST /api/chat."""
    mode: Literal["chat", "solve"]
    conversation_id: str
    message: str
    title: Optional[str] = Field(None, description="Intelligent AI-generated conversation title")
    request_id: Optional[str] = None
    intent_result: Optional[IntentResult] = None
    memories_used: List[str] = Field(default_factory=list)
    request_status: str = "completed"
    # Domain-aware fields
    domain_category: Optional[str] = None
    resolved_domain: Optional[str] = None
    # Fields to maintain 100% compatibility with existing solve UI / consumers
    final_synthesized_answer: Optional[str] = None
    final_answer: Optional[str] = None
    agent_execution_statuses: List[Any] = Field(default_factory=list)
    retrieved_sources: List[str] = Field(default_factory=list)
    selected_agents: List[str] = Field(default_factory=list)
    execution_trace: List[Dict[str, Any]] = Field(default_factory=list)
