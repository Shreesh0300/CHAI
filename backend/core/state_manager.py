"""
State manager and helper utilities for CHAI state manipulation.
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from backend.core.state import (
    CHAIState,
    create_initial_state,
    ExecutionTraceItem,
    register_agent_result,
    get_canonical_agent_result,
)


class StateManager:
    """Helper utilities for initializing, validating, and updating CHAIState."""

    @staticmethod
    def initialize(
        problem: str,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CHAIState:
        return create_initial_state(
            problem=problem,
            request_id=request_id,
            user_id=user_id,
            context=context,
            metadata=metadata,
        )

    @staticmethod
    def register_result(state: CHAIState, agent_name: str, result: Any) -> Dict[str, Any]:
        """Canonical update helper ensuring state[f'{agent}_result'] and state['agent_outputs'][agent] match."""
        return register_agent_result(state, agent_name, result)

    @staticmethod
    def get_result(state: CHAIState, agent_name: str) -> Optional[Any]:
        """Returns the canonical authoritative result for a given agent."""
        return get_canonical_agent_result(state, agent_name)

    @staticmethod
    def create_trace_item(
        agent: str,
        status: str,
        duration_ms: Optional[float] = None,
        details: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        item: Dict[str, Any] = {
            "agent": agent,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if duration_ms is not None:
            item["duration_ms"] = round(duration_ms, 2)
        if details:
            item["details"] = details
        if error:
            item["error"] = error
        return item


__all__ = [
    "CHAIState",
    "create_initial_state",
    "ExecutionTraceItem",
    "StateManager",
    "register_agent_result",
    "get_canonical_agent_result",
]
