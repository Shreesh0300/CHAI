"""
CHAI Real-Time Multi-Agent Execution Tracker Events & Pub/Sub Manager.

Provides:
- Typed ExecutionEvent schema for SSE streaming
- Agent metadata (display names, task descriptions, stage categorizations)
- Thread-safe ExecutionEventManager for buffering and broadcasting live events per request_id
- Safe error sanitization preventing leakage of credentials, prompts, or stack traces
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Literal, Set, AsyncIterator, Any
from pydantic import BaseModel, Field

from backend.shared.logger import get_logger

logger = get_logger(__name__)

EventStatus = Literal["pending", "running", "completed", "failed", "skipped", "paused", "cancelled"]


class RequestCancelledException(Exception):
    """Raised when an active generation is explicitly cancelled by the user."""

    def __init__(self, message: str = "Generation cancelled by user", request_id: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.request_id = request_id

AGENT_DESCRIPTIONS: Dict[str, str] = {
    "router": "Classifying query complexity and active domain lens",
    "information_acquisition": "Acquiring empirical external knowledge and data sources",
    "researcher": "Gathering empirical evidence and domain research",
    "strategist": "Formulating strategic options, commercial viability, and trade-offs",
    "engineer": "Architecting system design, components, and technical specifications",
    "guardian": "Evaluating safety risks, ethical boundaries, and privacy protection",
    "security": "Auditing threat models, access controls, and security hardening",
    "evaluator": "Evaluating feasibility, scoring trade-offs, and ranking options",
    "conflict_resolver": "Reconciling conflicting perspectives across agent proposals",
    "synthesizer": "Synthesizing unified, coherent recommendation",
    "reliability_monitor": "Auditing factual grounding and reasoning reliability",
    "output_validator": "Validating final response standards and contracts",
}

AGENT_DISPLAY_NAMES: Dict[str, str] = {
    "router": "Router",
    "information_acquisition": "Information Acquisition",
    "researcher": "Researcher Agent",
    "strategist": "Strategist Agent",
    "engineer": "Engineer Agent",
    "guardian": "Guardian Agent",
    "security": "Security Agent",
    "evaluator": "Evaluator Agent",
    "conflict_resolver": "Conflict Resolver",
    "synthesizer": "Synthesizer Agent",
    "reliability_monitor": "Reliability Monitor",
    "output_validator": "Output Validator",
}

FINALIZATION_AGENTS: Set[str] = {
    "evaluator",
    "conflict_resolver",
    "synthesizer",
    "reliability_monitor",
    "output_validator",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_error_message(err: Any) -> str:
    """Returns a safe, user-facing error message without secrets or stack traces."""
    if not err:
        return "Unknown error occurred"
    text = str(err).strip()
    lower = text.lower()
    if any(k in lower for k in ("api_key", "secret", "password", "token", "traceback", "private_key")):
        return "An internal execution error occurred. Details withheld for security."
    # Truncate overly long error strings
    if len(text) > 200:
        return text[:197] + "..."
    return text


class ExecutionEvent(BaseModel):
    """Structured execution event streamed via Server-Sent Events."""
    request_id: str
    event: str = Field(
        ...,
        description="Event kind: 'request_started', 'chat_mode_selected', 'agent_status', 'final_answer', 'request_failed'",
    )
    agent: Optional[str] = Field(None, description="Canonical agent identifier if agent event")
    stage: Optional[str] = Field(None, description="Workflow stage or agent name")
    status: EventStatus = Field(default="running", description="Status of the agent or request")
    timestamp: str = Field(default_factory=_iso_now, description="ISO-8601 timestamp")
    message: Optional[str] = Field(None, description="Human-readable safe task description or status update")
    duration_ms: Optional[float] = Field(None, description="Elapsed execution duration in milliseconds if completed/failed")
    error: Optional[str] = Field(None, description="Sanitized error description if failed")
    selected_agents: Optional[List[str]] = Field(None, description="List of agents chosen for this specific execution")
    domain: Optional[str] = Field(None, description="Resolved domain lens ('business', 'personal', 'software')")
    is_finalization: bool = Field(default=False, description="Whether this agent belongs to the finalization stage")
    final_answer: Optional[str] = Field(None, description="Delivered final answer text when ready")
    title: Optional[str] = Field(None, description="AI-generated conversation title")


class ExecutionSession:
    """Manages event history and active subscriber queues for a single solve request."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.created_at = time.time()
        self.events_history: List[ExecutionEvent] = []
        self.subscribers: List[asyncio.Queue[ExecutionEvent]] = []
        self.is_terminal = False
        self.selected_agents: List[str] = []
        self.lock = asyncio.Lock()

        # Pause and cancel state
        self.status: EventStatus = "running"
        self.pause_requested: bool = False
        self.cancel_requested: bool = False
        self.pause_event = asyncio.Event()
        self.pause_event.set()  # Initial state: unpaused / running
        self.cancel_event = asyncio.Event()
        self.in_flight_task: Optional[asyncio.Task] = None
        self.completed_agent_outputs: Dict[str, Any] = {}
        self.completed_statuses: List[Any] = []
        self.execution_trace: List[Dict[str, Any]] = []

    def request_pause(self) -> bool:
        """Suspends active request at safe stage boundary."""
        if self.is_terminal or self.cancel_requested:
            return False
        if not self.pause_requested:
            self.pause_requested = True
            self.pause_event.clear()
            self.status = "paused"
            return True
        return False

    def request_resume(self) -> bool:
        """Resumes a paused request."""
        if self.is_terminal or self.cancel_requested:
            return False
        if self.pause_requested:
            self.pause_requested = False
            self.pause_event.set()
            self.status = "running"
            return True
        return False

    def request_cancel(self) -> bool:
        """Terminates active request and stops further execution."""
        if self.cancel_requested:
            return False
        self.cancel_requested = True
        self.pause_requested = False
        self.pause_event.set()  # Release any waiting pause loop so it exits immediately
        self.cancel_event.set()
        self.status = "cancelled"
        self.is_terminal = True
        if self.in_flight_task and not self.in_flight_task.done():
            try:
                self.in_flight_task.cancel()
            except Exception as e:
                logger.debug(f"Could not cancel in-flight task for {self.request_id}: {e}")
        return True

    def add_subscriber(self) -> asyncio.Queue[ExecutionEvent]:
        q: asyncio.Queue[ExecutionEvent] = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def remove_subscriber(self, q: asyncio.Queue[ExecutionEvent]) -> None:
        if q in self.subscribers:
            self.subscribers.remove(q)

    def append_event(self, event: ExecutionEvent) -> None:
        self.events_history.append(event)
        if event.selected_agents:
            self.selected_agents = list(event.selected_agents)
        if event.event in ("final_answer", "request_failed", "request_cancelled"):
            self.is_terminal = True
        for q in list(self.subscribers):
            try:
                q.put_nowait(event)
            except Exception as e:
                logger.debug(f"Could not push event to subscriber queue: {e}")


class ExecutionEventManager:
    """
    Central manager for tracking live multi-agent execution events.
    Supports historical replay for late-connecting clients and real-time SSE broadcasts.
    """

    def __init__(self):
        self._sessions: Dict[str, ExecutionSession] = {}
        self._lock = asyncio.Lock()

    def get_or_create_session(self, request_id: str) -> ExecutionSession:
        if request_id not in self._sessions:
            self._sessions[request_id] = ExecutionSession(request_id)
        return self._sessions[request_id]

    def create_session(self, request_id: str) -> ExecutionSession:
        return self.get_or_create_session(request_id)

    def has_session(self, request_id: str) -> bool:
        return request_id in self._sessions

    def get_session(self, request_id: str) -> Optional[ExecutionSession]:
        return self._sessions.get(request_id)

    async def pause_request(self, request_id: str) -> bool:
        """Pauses the request associated with request_id at safe stage boundaries."""
        session = self.get_session(request_id)
        if not session:
            return False
        changed = session.request_pause()
        if changed:
            await self.emit(
                request_id=request_id,
                event="request_paused",
                status="paused",
                message="Generation paused",
            )
        return changed

    async def resume_request(self, request_id: str) -> bool:
        """Resumes a previously paused request."""
        session = self.get_session(request_id)
        if not session:
            return False
        changed = session.request_resume()
        if changed:
            await self.emit(
                request_id=request_id,
                event="request_resumed",
                status="running",
                message="Generation resumed",
            )
        return changed

    async def cancel_request(self, request_id: str) -> bool:
        """Aborts active generation and prevents future agent execution."""
        session = self.get_session(request_id)
        if not session:
            session = self.create_session(request_id)
        changed = session.request_cancel()
        if changed:
            await self.emit(
                request_id=request_id,
                event="request_cancelled",
                status="cancelled",
                message="Generation cancelled by user",
            )
        return changed

    def is_cancelled(self, request_id: Optional[str]) -> bool:
        if not request_id:
            return False
        session = self.get_session(request_id)
        return bool(session and session.cancel_requested)

    def is_paused(self, request_id: Optional[str]) -> bool:
        if not request_id:
            return False
        session = self.get_session(request_id)
        return bool(session and session.pause_requested)

    def check_cancelled(self, request_id: Optional[str]) -> None:
        if self.is_cancelled(request_id):
            raise RequestCancelledException(f"Request '{request_id}' cancelled by user", request_id=request_id)

    async def wait_if_paused(self, request_id: Optional[str]) -> None:
        if not request_id:
            return
        session = self.get_session(request_id)
        if not session:
            return
        if session.cancel_requested:
            raise RequestCancelledException(f"Request '{request_id}' cancelled by user", request_id=request_id)
        if session.pause_requested:
            logger.info(f"Execution for {request_id} paused. Waiting at safe stage boundary...")
            await session.pause_event.wait()
            if session.cancel_requested:
                raise RequestCancelledException(f"Request '{request_id}' cancelled by user", request_id=request_id)
            logger.info(f"Execution for {request_id} resumed.")

    async def emit(
        self,
        request_id: str,
        event: str,
        agent: Optional[str] = None,
        stage: Optional[str] = None,
        status: EventStatus = "running",
        message: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        selected_agents: Optional[List[str]] = None,
        domain: Optional[str] = None,
        final_answer: Optional[str] = None,
        title: Optional[str] = None,
        **kwargs: Any,
    ) -> ExecutionEvent:
        """Constructs, buffers, and broadcasts an execution event."""
        session = self.get_or_create_session(request_id)

        # Set helpful default message if omitted
        if not message:
            if agent and agent in AGENT_DESCRIPTIONS:
                if status == "running":
                    message = AGENT_DESCRIPTIONS[agent]
                elif status == "completed":
                    message = f"{AGENT_DISPLAY_NAMES.get(agent, agent.title())} completed"
                elif status == "failed":
                    message = f"{AGENT_DISPLAY_NAMES.get(agent, agent.title())} failed"
                elif status == "skipped":
                    message = f"{AGENT_DISPLAY_NAMES.get(agent, agent.title())} skipped"
            elif event == "request_started":
                message = "CHAI is coordinating its agents"
            elif event == "request_paused":
                message = "Generation paused"
            elif event == "request_resumed":
                message = "Generation resumed"
            elif event == "request_cancelled":
                message = "Generation cancelled"
            elif event == "conversation_title":
                message = f"Conversation title: {title}" if title else "Conversation title generated"
            elif event == "final_answer":
                message = "Final response ready"

        sanitized_err = sanitize_error_message(error) if error else None
        is_final = bool(agent and agent in FINALIZATION_AGENTS)

        evt = ExecutionEvent(
            request_id=request_id,
            event=event,
            agent=agent,
            stage=stage or agent,
            status=status,
            timestamp=_iso_now(),
            message=message,
            duration_ms=round(duration_ms, 2) if duration_ms is not None else None,
            error=sanitized_err,
            selected_agents=selected_agents,
            domain=domain,
            is_finalization=is_final,
            final_answer=final_answer,
            title=title,
        )

        session.append_event(evt)
        return evt

    async def subscribe(
        self,
        request_id: str,
        wait_for_init_seconds: float = 3.0,
    ) -> AsyncIterator[ExecutionEvent]:
        """
        Subscribes to live events for the specified request_id.
        Replays past buffered events first, then yields real-time updates.
        Raises KeyError if request_id does not exist and is not created within wait_for_init_seconds.
        """
        # Brief grace window in case client connects milliseconds before POST arrives
        start_wait = time.time()
        while request_id not in self._sessions:
            if time.time() - start_wait > wait_for_init_seconds:
                raise KeyError(f"Execution session '{request_id}' not found")
            await asyncio.sleep(0.05)

        session = self._sessions[request_id]
        queue = session.add_subscriber()

        # Replay buffered history
        for past_event in list(session.events_history):
            yield past_event

        # If already terminal, we are done
        if session.is_terminal:
            session.remove_subscriber(queue)
            return

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield event
                    if event.event in ("final_answer", "request_failed", "request_cancelled") or session.is_terminal:
                        break
                except asyncio.TimeoutError:
                    # Keepalive idle check; if session completed while waiting, exit
                    if session.is_terminal:
                        break
        finally:
            session.remove_subscriber(queue)

    def cleanup_old_sessions(self, max_age_seconds: float = 1800.0) -> int:
        """Removes sessions older than max_age_seconds to prevent memory growth."""
        now = time.time()
        to_del = [
            rid for rid, sess in self._sessions.items()
            if now - sess.created_at > max_age_seconds
        ]
        for rid in to_del:
            self._sessions.pop(rid, None)
        return len(to_del)


# Global singleton instance
execution_event_manager = ExecutionEventManager()

__all__ = [
    "ExecutionEvent",
    "ExecutionSession",
    "ExecutionEventManager",
    "execution_event_manager",
    "RequestCancelledException",
    "AGENT_DESCRIPTIONS",
    "AGENT_DISPLAY_NAMES",
    "FINALIZATION_AGENTS",
    "sanitize_error_message",
]

