"""
Shared State definition for CHAI (Coordinated Hybrid Agentic Intelligence).
Defines the central TypedDict and Pydantic models for LangGraph state passing.

Canonical Source of Truth Architecture:
- For each specialist agent, `state[f"{agent_name}_result"]` holds the authoritative,
  typed result instance returned by the agent.
- `state["agent_outputs"][agent_name]` is explicitly derived from `state[f"{agent_name}_result"]`
  via serialization (.model_dump() or dict) to ensure backwards compatibility with API and UI.
- Use `register_agent_result` to atomically update both representations and prevent silent divergence.
"""
from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid


class ExecutionTraceItem(TypedDict, total=False):
    agent: str
    status: str  # "started" | "completed" | "failed" | "skipped"
    timestamp: str
    duration_ms: Optional[float]
    details: Optional[str]
    error: Optional[str]


class CHAIState(TypedDict, total=False):
    """
    Central shared state passing through the CHAI LangGraph workflow.
    Agents communicate strictly via reading from and writing to this state.
    """
    request_id: str
    user_id: Optional[str]
    problem: str
    original_query: str
    context: Optional[str]
    route: str  # "simple" | "complex"
    complexity: str  # "low" | "medium" | "high"
    execution_status: str  # "pending" | "running" | "completed" | "failed"
    current_agent: Optional[str]
    completed_agents: List[str]
    failed_agents: List[str]
    agent_outputs: Dict[str, Any]
    research_result: Optional[Any]
    strategy_result: Optional[Any]
    engineer_result: Optional[Any]
    guardian_result: Optional[Any]
    security_result: Optional[Any]
    evaluator_result: Optional[Any]
    synthesis_result: Optional[Any]
    validation_result: Optional[Any]
    information_result: Optional[Any]
    acquired_information: List[Any]
    sources: List[str]
    conflicts: List[str]
    errors: List[str]
    execution_trace: List[Dict[str, Any]]
    final_answer: Optional[str]
    metadata: Dict[str, Any]


def create_initial_state(
    problem: str,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    context: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> CHAIState:
    """Creates a clean, normalized initial state for a new request."""
    req_id = request_id or str(uuid.uuid4())
    cleaned_problem = (problem or "").strip()
    return {
        "request_id": req_id,
        "user_id": user_id,
        "problem": cleaned_problem,
        "original_query": cleaned_problem,
        "context": context,
        "route": "",
        "complexity": "",
        "execution_status": "running",
        "current_agent": None,
        "completed_agents": [],
        "failed_agents": [],
        "agent_outputs": {},
        "research_result": None,
        "strategy_result": None,
        "engineer_result": None,
        "guardian_result": None,
        "security_result": None,
        "evaluator_result": None,
        "synthesis_result": None,
        "validation_result": None,
        "information_result": None,
        "acquired_information": [],
        "sources": [],
        "conflicts": [],
        "errors": [],
        "execution_trace": [],
        "final_answer": None,
        "metadata": metadata or {},
    }


AGENT_RESULT_KEYS: Dict[str, str] = {
    "researcher": "research_result",
    "strategist": "strategy_result",
    "engineer": "engineer_result",
    "guardian": "guardian_result",
    "security": "security_result",
    "evaluator": "evaluator_result",
    "synthesizer": "synthesis_result",
    "output_validator": "validation_result",
}


def register_agent_result(
    state: CHAIState,
    agent_name: str,
    result: Any,
) -> Dict[str, Any]:
    """
    Atomically registers an agent's result in the state.

    Canonical Rule:
    `state[canonical_key]` (e.g., `state["research_result"]`) is the authoritative typed result.
    `state["agent_outputs"][agent_name]` is explicitly derived from it.
    This guarantees that the two representations never silently diverge.
    """
    if hasattr(result, "model_dump"):
        serialized = result.model_dump()
    elif isinstance(result, dict):
        serialized = dict(result)
    else:
        serialized = result

    outputs = dict(state.get("agent_outputs", {}))
    outputs[agent_name] = serialized

    canonical_key = AGENT_RESULT_KEYS.get(agent_name, f"{agent_name}_result")
    updates: Dict[str, Any] = {
        canonical_key: result,
        "agent_outputs": outputs,
    }
    if canonical_key != f"{agent_name}_result":
        updates[f"{agent_name}_result"] = result

    return updates


def get_canonical_agent_result(state: CHAIState, agent_name: str) -> Optional[Any]:
    """
    Retrieves the authoritative result for a given agent.
    Checks the canonical typed key first, falling back to agent_outputs.
    """
    canonical_key = AGENT_RESULT_KEYS.get(agent_name, f"{agent_name}_result")
    return (
        state.get(canonical_key)
        or state.get(f"{agent_name}_result")
        or state.get("agent_outputs", {}).get(agent_name)
    )


__all__ = [
    "CHAIState",
    "create_initial_state",
    "ExecutionTraceItem",
    "register_agent_result",
    "get_canonical_agent_result",
]
