"""
Schemas for CHAI core coordinator, routing, execution state, and API models.
"""
from typing import List, Optional, Any, Dict, Literal
from pydantic import BaseModel, Field

from backend.core.state import (
    CHAIState,
    create_initial_state,
    ExecutionTraceItem,
    register_agent_result,
    get_canonical_agent_result,
)


RouteType = Literal["simple", "complex"]
ComplexityType = Literal["low", "medium", "high"]
ExecutionStatus = Literal["pending", "running", "completed", "failed"]


class RouteDecision(BaseModel):
    """Structured decision output from the Router module."""
    route: RouteType = Field(..., description="Selected execution path ('simple' or 'complex')")
    complexity: ComplexityType = Field(..., description="Estimated query complexity ('low', 'medium', or 'high')")
    reasoning: str = Field(..., description="Deterministic rationale for route selection")
    required_agents: List[str] = Field(default_factory=list, description="Specialized agents required for this route")


class AgentExecutionStatus(BaseModel):
    """Status record for an individual agent execution."""
    agent_name: str
    status: str
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    timestamp: Optional[str] = None


class SolveRequest(BaseModel):
    """Input payload for /api/solve."""
    problem: str = Field(..., description="The user's problem or query.")
    user_id: Optional[str] = Field(None, description="Optional user identifier.")
    context: Optional[str] = Field(None, description="Optional environmental or domain context.")


class CHAIExecutionResult(BaseModel):
    """Complete strongly typed result model for a CHAI coordination run."""
    request_id: str
    user_id: Optional[str] = None
    problem: str
    original_query: str
    context: Optional[str] = None
    route: str
    complexity: str
    execution_status: str
    current_agent: Optional[str] = None
    completed_agents: List[str] = Field(default_factory=list)
    failed_agents: List[str] = Field(default_factory=list)
    agent_outputs: Dict[str, Any] = Field(default_factory=dict)
    research_result: Optional[Any] = None
    strategy_result: Optional[Any] = None
    engineer_result: Optional[Any] = None
    guardian_result: Optional[Any] = None
    security_result: Optional[Any] = None
    evaluator_result: Optional[Any] = None
    synthesis_result: Optional[Any] = None
    validation_result: Optional[Any] = None
    information_result: Optional[Any] = None
    acquired_information: List[Any] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    execution_trace: List[Dict[str, Any]] = Field(default_factory=list)
    final_answer: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FinalResponse(BaseModel):
    """
    HTTP response model for /api/solve.
    Maintains complete backward compatibility with existing tests and UI.
    """
    request_id: Optional[str] = None
    request_status: str = "completed"
    status: Optional[str] = None
    route: Optional[str] = None
    complexity: Optional[str] = None
    selected_agents: List[str] = Field(default_factory=list)
    agent_outputs: Dict[str, Any] = Field(default_factory=dict)
    retrieved_sources: List[str] = Field(default_factory=list)
    acquired_information: List[Any] = Field(default_factory=list)
    agent_execution_statuses: List[AgentExecutionStatus] = Field(default_factory=list)
    evaluation_findings: Optional[Any] = None
    security_findings: Optional[Any] = None
    detected_conflicts: List[str] = Field(default_factory=list)
    final_synthesized_answer: Optional[str] = None
    final_answer: Optional[str] = None
    synthesis_result: Optional[Any] = None
    validation_result: Optional[Any] = None
    execution_trace: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    limitations: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if self.status is None:
            self.status = self.request_status
        if self.request_status is None:
            self.request_status = self.status or "completed"


from backend.core.contracts import (  # noqa: E402
    AgentResult,
    SynthesisResult,
    FinalResult,
    ValidationResult,
    ResearcherInputContract,
    StrategistInputContract,
    EngineerInputContract,
    GuardianInputContract,
    SecurityInputContract,
    EvaluatorInputContract,
    SynthesizerInputContract,
    ResearcherInput,
    StrategistInput,
    EngineerInput,
    GuardianInput,
    SecurityInput,
    EvaluatorInput,
    SynthesizerInput,
)

__all__ = [
    "RouteType",
    "ComplexityType",
    "ExecutionStatus",
    "RouteDecision",
    "AgentExecutionStatus",
    "SolveRequest",
    "CHAIExecutionResult",
    "FinalResponse",
    "CHAIState",
    "create_initial_state",
    "ExecutionTraceItem",
    "AgentResult",
    "SynthesisResult",
    "FinalResult",
    "ValidationResult",
    "ResearcherInputContract",
    "StrategistInputContract",
    "EngineerInputContract",
    "GuardianInputContract",
    "SecurityInputContract",
    "EvaluatorInputContract",
    "SynthesizerInputContract",
    "ResearcherInput",
    "StrategistInput",
    "EngineerInput",
    "GuardianInput",
    "SecurityInput",
    "EvaluatorInput",
    "SynthesizerInput",
]
