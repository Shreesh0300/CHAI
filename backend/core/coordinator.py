"""
Coordinator module for CHAI (Coordinated Hybrid Agentic Intelligence).
Orchestrates multi-agent execution across Information Acquisition,
domain specialist agents, Conflict Resolver, Synthesizer,
Reliability Monitor, and Output Validator.
"""
from datetime import datetime, timezone
import asyncio
import os
import time
import uuid
from typing import Optional, Any, Dict, List, Set

from backend.core.schemas import (
    SolveRequest,
    FinalResponse,
    AgentExecutionStatus,
    CHAIExecutionResult,
    RouteDecision,
)
from backend.core.execution_events import (
    execution_event_manager,
    AGENT_DESCRIPTIONS,
    AGENT_DISPLAY_NAMES,
    EventStatus,
    sanitize_error_message,
    RequestCancelledException,
)
from backend.shared.llm_client import llm_client
from backend.core.state import (
    create_initial_state,
    CHAIState,
    register_agent_result,
    get_canonical_agent_result,
)
from backend.core.router import (
    route_request,
    resolve_domain,
    is_simple_query,
    ROUTE_SIMPLE,
    ROUTE_COMPLEX,
)
from backend.core.domain_lenses import normalize_domain
from backend.core.workflow import build_chai_workflow
from backend.information.service import InformationAcquisitionService
from backend.agents.researcher.models import Source
from backend.agents.researcher.agent import ResearcherAgent
from backend.agents.strategist.agent import StrategistAgent
from backend.agents.engineer.agent import EngineerAgent
from backend.agents.guardian.agent import GuardianAgent
from backend.agents.security.agent import SecurityAgent
from backend.agents.evaluator.agent import EvaluatorAgent
from backend.agents.conflict_resolver.agent import ConflictResolverAgent
from backend.agents.synthesizer.agent import SynthesizerAgent
from backend.agents.reliability_monitor.agent import ReliabilityMonitorAgent
from backend.agents.reliability_monitor.schemas import ReliabilityAction
from backend.validation.output_validator import OutputValidator, OutputValidationResult
from backend.synthesis.response_formatter import format_user_facing_response, normalize_unicode_escapes
from backend.shared.logger import get_logger

logger = get_logger(__name__)

CANONICAL_AGENTS = [
    "researcher",
    "strategist",
    "engineer",
    "guardian",
    "security",
    "evaluator",
    "conflict_resolver",
    "synthesizer",
    "reliability_monitor",
]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CHAICoordinator:
    """
    CHAI Coordinator: central orchestrator for multi-agent workflows.
    Ensures:
    - Central orchestration: agents never invoke one another directly.
    - Information Acquisition collects external knowledge without Coordinator being source-specific.
    - Specialist findings are cleanly validated, reconciled, monitored, and delivered.
    - Backward-compatible LangGraph compilation via `self.graph`.
    """

    def __init__(
        self,
        researcher: Optional[Any] = None,
        strategist: Optional[Any] = None,
        engineer: Optional[Any] = None,
        guardian: Optional[Any] = None,
        security: Optional[Any] = None,
        evaluator: Optional[Any] = None,
        conflict_resolver: Optional[Any] = None,
        synthesizer: Optional[Any] = None,
        reliability_monitor: Optional[Any] = None,
        output_validator: Optional[Any] = None,
        information_acquisition: Optional[Any] = None,
        direct_llm: Optional[Any] = None,
        **kwargs: Any,
    ):
        self.information_acquisition = information_acquisition or InformationAcquisitionService()
        self.researcher = researcher or ResearcherAgent()
        self.strategist = strategist or StrategistAgent()
        self.engineer = engineer or EngineerAgent()
        self.guardian = guardian or GuardianAgent()
        self.security = security or SecurityAgent()
        self.evaluator = evaluator or EvaluatorAgent()
        self.conflict_resolver = conflict_resolver or ConflictResolverAgent()
        self.synthesizer = synthesizer or SynthesizerAgent()
        self.reliability_monitor = reliability_monitor or ReliabilityMonitorAgent()
        self.output_validator = output_validator or OutputValidator()
        self.direct_llm = direct_llm

        self._agent_instances = {
            "information_acquisition": self.information_acquisition,
            "researcher": self.researcher,
            "strategist": self.strategist,
            "engineer": self.engineer,
            "guardian": self.guardian,
            "security": self.security,
            "evaluator": self.evaluator,
            "conflict_resolver": self.conflict_resolver,
            "synthesizer": self.synthesizer,
            "reliability_monitor": self.reliability_monitor,
            "output_validator": self.output_validator,
        }
        self._compiled_graph = None

    def build_graph(self) -> Any:
        """Constructs and returns the compiled LangGraph workflow executable."""
        return build_chai_workflow(self._agent_instances)

    @property
    def graph(self) -> Any:
        """Lazily builds and caches the compiled LangGraph workflow."""
        if self._compiled_graph is None:
            self._compiled_graph = self.build_graph()
        return self._compiled_graph

    async def solve(self, request: SolveRequest) -> FinalResponse:
        """Alias for process_request."""
        return await self.process_request(request)

    async def _emit_agent(
        self,
        request_id: Optional[str],
        agent: str,
        status: EventStatus,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        if not request_id:
            return
        try:
            await execution_event_manager.emit(
                request_id=request_id,
                event="agent_status",
                agent=agent,
                status=status,
                duration_ms=duration_ms,
                error=error,
                message=message,
            )
        except Exception as e:
            logger.debug(f"Could not emit event for {agent}: {e}")

    def _build_cancelled_response(
        self,
        request: SolveRequest,
        req_id: str,
        agent_outputs: Dict[str, Any],
        execution_statuses: List[AgentExecutionStatus],
        execution_trace: List[Dict[str, Any]],
        selected_agents: Optional[List[str]] = None,
        retrieved_sources: Optional[List[str]] = None,
        acquired_info: Optional[List[Any]] = None,
        domain_category: Optional[str] = None,
        resolved_domain: Optional[str] = None,
    ) -> FinalResponse:
        cancel_msg = "Generation cancelled by user."
        execution_trace.append({
            "agent": "coordinator",
            "stage": "coordinator",
            "status": "cancelled",
            "timestamp": _iso_now(),
            "details": cancel_msg,
        })
        return FinalResponse(
            request_id=req_id,
            conversation_id=getattr(request, "conversation_id", None),
            request_status="cancelled",
            status="cancelled",
            route="complex" if selected_agents else "simple",
            complexity="high" if selected_agents else "low",
            selected_agents=selected_agents or [],
            agent_outputs=agent_outputs,
            retrieved_sources=retrieved_sources or [],
            acquired_information=acquired_info or [],
            agent_execution_statuses=execution_statuses,
            final_synthesized_answer=cancel_msg,
            final_answer=cancel_msg,
            execution_trace=execution_trace,
            errors=[],
            domain_category=domain_category,
            resolved_domain=resolved_domain,
        )

    async def coordinate(self, request: SolveRequest) -> FinalResponse:
        """Alias for process_request."""
        return await self.process_request(request)

    async def process_request(self, request: SolveRequest) -> FinalResponse:
        """Executes a request through the coordinated multi-agent workflow."""
        logger.info(f"Coordinator: processing request: {request.problem}")

        agent_outputs: Dict[str, Any] = {}
        execution_statuses: List[AgentExecutionStatus] = []
        execution_trace: List[Dict[str, Any]] = []
        acquired_info: List[Any] = []
        retrieved_sources: List[str] = []
        selected_agents: List[str] = []
        domain_category: Optional[str] = None
        resolved_domain: Optional[str] = None

        req_id = getattr(request, "request_id", None) or str(uuid.uuid4())
        request.request_id = req_id
        session = execution_event_manager.create_session(req_id)
        try:
            session.in_flight_task = asyncio.current_task()
        except Exception:
            pass

        async def _check_cancel_or_pause() -> bool:
            if execution_event_manager.is_cancelled(req_id):
                return True
            await execution_event_manager.wait_if_paused(req_id)
            if execution_event_manager.is_cancelled(req_id):
                return True
            return False

        async def _check_or_cancel() -> Optional[FinalResponse]:
            if await _check_cancel_or_pause():
                return self._build_cancelled_response(
                    request=request,
                    req_id=req_id,
                    agent_outputs=agent_outputs,
                    execution_statuses=execution_statuses,
                    execution_trace=execution_trace,
                    selected_agents=selected_agents,
                    retrieved_sources=retrieved_sources,
                    acquired_info=acquired_info,
                    domain_category=domain_category,
                    resolved_domain=resolved_domain,
                )
            return None

        # Check conversation context if conversation_id is provided
        conversation_id = getattr(request, "conversation_id", None)
        user_id = getattr(request, "user_id", None) or "guest_default"
        conversation_context = getattr(request, "context", None)
        if not conversation_context and conversation_id:
            try:
                from backend.memory.context import context_manager
                conversation_context = await context_manager.build_solve_context(
                    user_id=user_id,
                    problem=request.problem,
                    conversation_id=conversation_id,
                    session_id=getattr(request, "session_id", None),
                )
            except Exception as e:
                logger.debug(f"Could not load conversation context: {e}")

        # Initialize canonical state tracking
        state = create_initial_state(
            problem=request.problem,
            user_id=user_id,
            context=conversation_context,
        )
        state["request_id"] = req_id

        # -------------------------------------------------------------
        # Determine Route and Selected Agents
        # -------------------------------------------------------------
        route_decision: Optional[RouteDecision] = None
        req_mode = (getattr(request, "mode", None) or "ask").lower().strip()

        if request.selected_agents is not None:
            honor_explicit_agents = True
        else:
            honor_explicit_agents = False

        if honor_explicit_agents and request.selected_agents is not None:
            selected_agents = [a.lower().strip() for a in request.selected_agents]
            route = "simple" if not selected_agents else "complex"
            complexity = "low" if not selected_agents else "high"
        else:
            # ASK mode (default): Router is the final authority
            route_decision = route_request(request.problem, conversation_context)
            if req_mode == "agent":
                route = "complex"
                complexity = "high"
            else:
                route = route_decision.route
                complexity = route_decision.complexity

            if route == "simple":
                selected_agents = []
            else:
                # Domain-aware adaptive agent selection:
                # Personal/career decision: exclude irrelevant engineer/security agents unless technical requirements exist
                has_tech = any(w in request.problem.lower() for w in ["tech", "software", "engineer", "code", "architecture", "platform", "system", "database", "security"])
                if route_decision.domain == "personal_career" and not has_tech:
                    selected_agents = [
                        "researcher",
                        "strategist",
                        "guardian",
                        "evaluator",
                        "conflict_resolver",
                        "synthesizer",
                        "reliability_monitor",
                    ]
                else:
                    selected_agents = list(CANONICAL_AGENTS)

        # -------------------------------------------------------------
        # Resolve Domain (DOMAIN LENS)
        # RULE: EXPLICIT USER CATEGORY > AUTOMATIC CLASSIFICATION
        # -------------------------------------------------------------
        explicit_category = getattr(request, "category", None)
        # When complex route was already forced by patterns in route_decision, we still
        # respect the user’s explicit category override for domain instruction.
        auto_domain = route_decision.domain if route_decision else "general"
        # resolve_domain re-detects or maps from explicit category
        domain_category, domain_instruction = resolve_domain(
            problem=request.problem,
            category=explicit_category,
            context=conversation_context,
        )
        # If user chose AUTO but route_decision already detected a precise domain,
        # prefer route_decision’s detection over "general" fallback.
        if (explicit_category is None or explicit_category.upper() == "AUTO") and auto_domain != "general":
            domain_category = auto_domain
            from backend.core.router import _DOMAIN_INSTRUCTIONS
            domain_instruction = _DOMAIN_INSTRUCTIONS.get(auto_domain, _DOMAIN_INSTRUCTIONS["general"])

        # Store into state so every downstream agent/node can read it
        state["domain_category"] = domain_category
        state["domain_instruction"] = domain_instruction
        resolved_domain = normalize_domain(domain_category)
        state["resolved_domain"] = resolved_domain

        logger.info(
            f"DOMAIN LENS: explicit_category={explicit_category!r} → "
            f"resolved_domain={resolved_domain!r} (internal category={domain_category!r})"
        )

        # Prepend domain instruction to the conversation context that agents receive
        if domain_instruction:
            if conversation_context and conversation_context.strip():
                conversation_context = f"{domain_instruction}\n\n{conversation_context.strip()}"
            else:
                conversation_context = domain_instruction

        execution_trace.append({
            "agent": "router",
            "stage": "router",
            "status": "completed",
            "timestamp": _iso_now(),
            "duration_ms": 0.0,
            "route": route,
        })

        # -------------------------------------------------------------
        # Simple Direct Response Path (No specialized agents invoked)
        # -------------------------------------------------------------
        if route == "simple" or (request.selected_agents is not None and not selected_agents):
            cancelled_res = await _check_or_cancel()
            if cancelled_res:
                return cancelled_res
            await execution_event_manager.emit(
                request_id=req_id,
                event="chat_mode_selected",
                status="running",
                message="CHAI is responding...",
            )
            t0 = time.monotonic()
            direct_text = ""
            try:
                if self.direct_llm:
                    if hasattr(self.direct_llm, "generate_content"):
                        direct_text = await self.direct_llm.generate_content(request.problem)
                    else:
                        direct_text = await self.direct_llm(request.problem)
                elif os.getenv("CHAI_MOCK_MODE", "").lower() in ("true", "1", "yes") and not llm_client.api_key:
                    direct_text = f"Direct response provided for: {request.problem}"
                else:
                    prompt = (
                        "You are CHAI, an intelligent, helpful, accurate, and concise AI assistant.\n"
                        "Answer the following question directly, clearly, and naturally in 1-4 sentences.\n"
                        "- Provide the direct answer in the very first sentence.\n"
                        "- Keep the response concise (1-4 sentences) unless more detail was specifically requested.\n"
                        "- Do NOT repeat or rephrase the question.\n"
                        "- Do NOT use Markdown headings, sections, or bullet lists for simple questions.\n"
                        "- Do NOT mention any agents, internal systems, or multi-agent pipelines.\n"
                        "- Maintain flawless grammar, punctuation, and natural English.\n\n"
                    )
                    if conversation_context and conversation_context.strip():
                        prompt += f"[CONVERSATION CONTEXT]\n{conversation_context.strip()}\n\n"
                    prompt += f"Question: {request.problem}"
                    direct_text = await llm_client.generate_content(prompt)
                    if not direct_text or direct_text.strip() == "Mock response: API key not configured.":
                        direct_text = f"Direct response provided for: {request.problem}"
            except Exception as e:
                from backend.core.execution_events import RequestCancelledException
                if isinstance(e, (RequestCancelledException, asyncio.CancelledError)) or execution_event_manager.is_cancelled(req_id):
                    return self._build_cancelled_response(
                        request=request,
                        req_id=req_id,
                        agent_outputs=agent_outputs,
                        execution_statuses=execution_statuses,
                        execution_trace=execution_trace,
                        selected_agents=selected_agents,
                        retrieved_sources=retrieved_sources,
                        acquired_info=acquired_info,
                        domain_category=domain_category,
                        resolved_domain=resolved_domain,
                    )
                if self.direct_llm is not None:
                    logger.error(f"Direct LLM call failed: {e}")
                    execution_trace.append({
                        "agent": "direct_llm",
                        "stage": "direct_llm",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                        "error": str(e),
                    })
                    await execution_event_manager.emit(
                        request_id=req_id,
                        event="request_failed",
                        status="failed",
                        error=str(e),
                        message="Error generating direct response",
                    )
                    return FinalResponse(
                        request_id=getattr(request, "request_id", None) or state.get("request_id"),
                        request_status="failed",
                        status="failed",
                        route="simple",
                        complexity=complexity,
                        selected_agents=[],
                        agent_outputs={},
                        retrieved_sources=[],
                        acquired_information=[],
                        agent_execution_statuses=[],
                        evaluation_findings=None,
                        security_findings=None,
                        detected_conflicts=[],
                        final_synthesized_answer=f"Error generating direct response: {e}",
                        final_answer=f"Error generating direct response: {e}",
                        execution_trace=execution_trace,
                        errors=[str(e)],
                        limitations=[],
                        metadata={"route": "simple"},
                    )
                logger.warning(f"Direct LLM call failed ({e}); utilizing resilient direct fallback.")
                direct_text = f"Direct response provided for: {request.problem}"

            if execution_event_manager.is_cancelled(req_id):
                return self._build_cancelled_response(
                    request=request,
                    req_id=req_id,
                    agent_outputs=agent_outputs,
                    execution_statuses=execution_statuses,
                    execution_trace=execution_trace,
                    selected_agents=selected_agents,
                    retrieved_sources=retrieved_sources,
                    acquired_info=acquired_info,
                    domain_category=domain_category,
                    resolved_domain=resolved_domain,
                )

            sanitized_direct = normalize_unicode_escapes(direct_text if isinstance(direct_text, str) else str(direct_text))
            user_facing_direct = format_user_facing_response(
                query=request.problem,
                raw_answer=sanitized_direct,
                route="simple",
                domain=route_decision.domain if route_decision else "general",
                requested_depth=route_decision.requested_depth if route_decision else "brief",
            )
            user_facing_direct = normalize_unicode_escapes(user_facing_direct)

            if conversation_id:
                try:
                    from backend.memory.store import memory_store
                    await memory_store.add_message(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        role="user",
                        content=request.problem,
                    )
                    await memory_store.add_message(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        role="assistant",
                        content=user_facing_direct,
                    )
                except Exception as me:
                    logger.debug(f"Could not persist conversation history: {me}")

            execution_trace.append({
                "agent": "direct_llm",
                "stage": "direct_llm",
                "status": "completed",
                "timestamp": _iso_now(),
                "duration_ms": round((time.monotonic() - t0) * 1000, 2),
            })

            await execution_event_manager.emit(
                request_id=req_id,
                event="final_answer",
                status="completed",
                final_answer=user_facing_direct,
                message="Response delivered",
            )

            return FinalResponse(
                request_id=getattr(request, "request_id", None) or state.get("request_id"),
                conversation_id=conversation_id,
                request_status="completed",
                status="completed",
                route="simple",
                complexity=complexity,
                selected_agents=[],
                agent_outputs={},
                retrieved_sources=[],
                acquired_information=[],
                agent_execution_statuses=[],
                evaluation_findings=None,
                security_findings=None,
                detected_conflicts=[],
                final_synthesized_answer=sanitized_direct,
                final_answer=user_facing_direct,
                execution_trace=execution_trace,
                errors=[],
                limitations=[],
                metadata={"route": "simple"},
                domain_category=domain_category,
                resolved_domain=state.get("resolved_domain") or normalize_domain(domain_category),
            )

        # -------------------------------------------------------------
        # Complex Multi-Agent Pipeline
        # -------------------------------------------------------------
        full_selected = list(selected_agents)
        if "output_validator" not in full_selected:
            full_selected.append("output_validator")

        await execution_event_manager.emit(
            request_id=req_id,
            event="request_started",
            status="running",
            selected_agents=full_selected,
            domain=resolved_domain,
            message="CHAI is coordinating its agents",
        )

        for unselected_agent in CANONICAL_AGENTS:
            if unselected_agent not in selected_agents:
                await self._emit_agent(
                    req_id,
                    agent=unselected_agent,
                    status="skipped",
                    message=f"{AGENT_DISPLAY_NAMES.get(unselected_agent, unselected_agent.title())} skipped for this domain",
                )

        # 0. Information Acquisition
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        should_acquire = (
            (route_decision is None or route_decision.requires_external_information)
            and self.information_acquisition is not None
            and "researcher" in selected_agents
        )

        if should_acquire:
            t0 = time.monotonic()
            await self._emit_agent(req_id, "information_acquisition", "running")
            try:
                # Select source types: avoid calling irrelevant external financial/currency APIs for general queries
                target_types = None
                p_lower = request.problem.lower()
                is_finance_fx = any(k in p_lower for k in ("currency", "exchange rate", "forex", "usd", "eur", "financial rate", "weather"))
                if not is_finance_fx and not os.getenv("API_SOURCE_URL"):
                    target_types = ["web", "model"]

                info_res = await self.information_acquisition.acquire(
                    request.problem,
                    source_types=target_types,
                )
                if hasattr(info_res, "items"):
                    raw_items = info_res.items
                elif isinstance(info_res, list):
                    raw_items = info_res
                else:
                    raw_items = []
                acquired_info = [
                    it.model_dump() if hasattr(it, "model_dump") else (dict(it) if isinstance(it, dict) else it)
                    for it in raw_items
                ]
                for item in raw_items:
                    src = getattr(item, "source", None) or getattr(item, "url", None)
                    if not src and isinstance(item, dict):
                        src = item.get("source") or item.get("url")
                    if src and src not in retrieved_sources:
                        retrieved_sources.append(src)
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                execution_trace.append({
                    "agent": "information_acquisition",
                    "stage": "information_acquisition",
                    "status": "completed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "details": f"Acquired {len(acquired_info)} information items.",
                })
                agent_outputs["information_acquisition"] = {
                    "agent": "information_acquisition",
                    "status": "completed",
                    "acquired_info": acquired_info,
                    "retrieved_sources": retrieved_sources,
                }
                session.completed_agent_outputs["information_acquisition"] = agent_outputs["information_acquisition"]
                await self._emit_agent(
                    req_id,
                    "information_acquisition",
                    "completed",
                    duration_ms=duration_ms,
                    message=f"Acquired {len(acquired_info)} information items",
                )
            except Exception as e:
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                logger.warning(f"Information Acquisition execution error: {e}")
                execution_trace.append({
                    "agent": "information_acquisition",
                    "stage": "information_acquisition",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                await self._emit_agent(
                    req_id,
                    "information_acquisition",
                    "failed",
                    duration_ms=duration_ms,
                    error=str(e),
                )
        elif self.information_acquisition is not None and "researcher" in selected_agents and not should_acquire:
            execution_trace.append({
                "agent": "information_acquisition",
                "stage": "information_acquisition",
                "status": "skipped",
                "timestamp": _iso_now(),
                "duration_ms": 0.0,
                "details": "External information not required for this query.",
            })
            await self._emit_agent(
                req_id,
                "information_acquisition",
                "skipped",
                duration_ms=0.0,
                message="External information acquisition skipped",
            )

        # 1. Researcher
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        researcher_fatal_stop = False
        if "researcher" in selected_agents:
            t0 = time.monotonic()
            await self._emit_agent(req_id, "researcher", "running")
            try:
                provenance_sources = []
                for item in acquired_info:
                    if isinstance(item, dict):
                        title = item.get("title") or item.get("source", "source")
                        url = item.get("url")
                        stype = item.get("source_type", "web")
                    else:
                        title = getattr(item, "title", None) or getattr(item, "source", "source")
                        url = getattr(item, "url", None)
                        stype = getattr(item, "source_type", "web")
                    provenance_sources.append(Source(title=title, url=url, source_type=stype))

                context_val = getattr(request, "context", None)
                try:
                    res_output = await self.researcher.run(
                        problem=request.problem,
                        context=context_val,
                        acquired_information=acquired_info,
                        sources=provenance_sources or None,
                        domain=resolved_domain,
                    )
                except TypeError:
                    try:
                        res_output = await self.researcher.run(
                            request.problem,
                            context=context_val,
                            domain=resolved_domain,
                        )
                    except TypeError:
                        res_output = await self.researcher.run(request.problem)

                res_dump = res_output.model_dump() if hasattr(res_output, "model_dump") else dict(res_output)
                status_val = getattr(res_output, "status", None) or res_dump.get("status")
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                if str(status_val).lower() in ("completed", "success"):
                    agent_outputs["researcher"] = res_dump
                    session.completed_agent_outputs["researcher"] = res_dump
                    register_agent_result(state, "researcher", res_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="researcher",
                            status="success",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "researcher",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                    })
                    await self._emit_agent(req_id, "researcher", "completed", duration_ms=duration_ms)
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="researcher",
                            status="failed",
                            error="Researcher returned failed status",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "researcher",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                        "error": "Researcher returned failed status",
                    })
                    await self._emit_agent(
                        req_id,
                        "researcher",
                        "failed",
                        duration_ms=duration_ms,
                        error="Researcher returned failed status",
                    )
            except Exception as e:
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                if isinstance(e, RuntimeError):
                    researcher_fatal_stop = True
                logger.error(f"Researcher execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="researcher",
                        status="failed",
                        error=str(e),
                        duration_ms=duration_ms,
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "researcher",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                await self._emit_agent(req_id, "researcher", "failed", duration_ms=duration_ms, error=str(e))

        # Hard-stop on Researcher fatal failure during complex pipeline execution
        if researcher_fatal_stop:
            if request.selected_agents is None:
                err_text = "Researcher agent failed. Unable to continue the requested analysis."
                await execution_event_manager.emit(
                    request_id=req_id,
                    event="request_failed",
                    status="failed",
                    error=err_text,
                    message=err_text,
                )
                return FinalResponse(
                    request_id=getattr(request, "request_id", None) or state.get("request_id"),
                    request_status="failed",
                    status="failed",
                    route="complex",
                    complexity=complexity,
                    selected_agents=["researcher"],
                    agent_outputs={},
                    retrieved_sources=[],
                    acquired_information=[],
                    agent_execution_statuses=execution_statuses,
                    final_synthesized_answer=err_text,
                    final_answer=err_text,
                    execution_trace=execution_trace,
                    errors=[err_text],
                )

        # 2. Strategist
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        if "strategist" in selected_agents:
            t0 = time.monotonic()
            await self._emit_agent(req_id, "strategist", "running")
            research_data = agent_outputs.get("researcher", {})
            context_for_strat = {"researcher_output": research_data, "researcher": research_data}
            try:
                try:
                    strat_output = await self.strategist.run(
                        problem=request.problem,
                        research=research_data,
                        context=context_for_strat,
                        domain=resolved_domain,
                    )
                except TypeError:
                    try:
                        strat_output = await self.strategist.run(
                            problem=request.problem,
                            research=research_data,
                            context=context_for_strat,
                        )
                    except TypeError:
                        try:
                            strat_output = await self.strategist.run(request.problem, domain=resolved_domain)
                        except TypeError:
                            strat_output = await self.strategist.run(request.problem)

                strat_dump = strat_output.model_dump() if hasattr(strat_output, "model_dump") else dict(strat_output)
                status_val = getattr(strat_output, "status", None) or strat_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                if val_str.lower() not in ("failed", "error"):
                    agent_outputs["strategist"] = strat_dump
                    session.completed_agent_outputs["strategist"] = strat_dump
                    try:
                        register_agent_result(state, "strategist", strat_output)
                    except Exception:
                        pass
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="strategist",
                            status="success",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "strategist",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                    })
                    await self._emit_agent(req_id, "strategist", "completed", duration_ms=duration_ms)
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="strategist",
                            status="failed",
                            error="Strategist returned failed status",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "strategist",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                        "error": "Strategist returned failed status",
                    })
                    await self._emit_agent(
                        req_id,
                        "strategist",
                        "failed",
                        duration_ms=duration_ms,
                        error="Strategist returned failed status",
                    )
            except Exception as e:
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                logger.error(f"Strategist execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="strategist",
                        status="failed",
                        error=str(e),
                        duration_ms=duration_ms,
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "strategist",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                await self._emit_agent(req_id, "strategist", "failed", duration_ms=duration_ms, error=str(e))

        # 3. Engineer
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        if "engineer" in selected_agents:
            t0 = time.monotonic()
            await self._emit_agent(req_id, "engineer", "running")
            context_for_eng = {
                "researcher": agent_outputs.get("researcher"),
                "strategist": agent_outputs.get("strategist"),
            }
            try:
                try:
                    eng_output = await self.engineer.run(request.problem, context=context_for_eng, domain=resolved_domain)
                except TypeError:
                    try:
                        eng_output = await self.engineer.run(request.problem, context=context_for_eng)
                    except TypeError:
                        try:
                            eng_output = await self.engineer.run(request.problem, domain=resolved_domain)
                        except TypeError:
                            eng_output = await self.engineer.run(request.problem)

                eng_dump = eng_output.model_dump() if hasattr(eng_output, "model_dump") else dict(eng_output)
                status_val = (
                    getattr(eng_output, "status", None)
                    or eng_dump.get("status")
                    or (eng_dump.get("engineer_result") or {}).get("status")
                    or ("completed" if eng_dump.get("technical_architecture") else None)
                )
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    agent_outputs["engineer"] = eng_dump
                    session.completed_agent_outputs["engineer"] = eng_dump
                    register_agent_result(state, "engineer", eng_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="engineer",
                            status="success",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "engineer",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                    })
                    await self._emit_agent(req_id, "engineer", "completed", duration_ms=duration_ms)
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="engineer",
                            status="failed",
                            error="Engineer returned failed status",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "engineer",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                        "error": "Engineer returned failed status",
                    })
                    await self._emit_agent(
                        req_id,
                        "engineer",
                        "failed",
                        duration_ms=duration_ms,
                        error="Engineer returned failed status",
                    )
            except Exception as e:
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                logger.error(f"Engineer execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="engineer",
                        status="failed",
                        error=str(e),
                        duration_ms=duration_ms,
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "engineer",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                await self._emit_agent(req_id, "engineer", "failed", duration_ms=duration_ms, error=str(e))

        # 4. Guardian
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        if "guardian" in selected_agents:
            t0 = time.monotonic()
            await self._emit_agent(req_id, "guardian", "running")
            context_for_guard = {
                "engineer": agent_outputs.get("engineer"),
                "strategist": agent_outputs.get("strategist"),
                "researcher": agent_outputs.get("researcher"),
            }
            try:
                try:
                    guard_output = await self.guardian.run(request.problem, context=context_for_guard, domain=resolved_domain)
                except TypeError:
                    try:
                        guard_output = await self.guardian.run(request.problem, context=context_for_guard)
                    except TypeError:
                        try:
                            guard_output = await self.guardian.run(request.problem, domain=resolved_domain)
                        except TypeError:
                            guard_output = await self.guardian.run(request.problem)

                guard_dump = guard_output.model_dump() if hasattr(guard_output, "model_dump") else dict(guard_output)
                status_val = (
                    getattr(guard_output, "status", None)
                    or guard_dump.get("status")
                    or (guard_dump.get("guardian_result") or {}).get("status")
                    or ("completed" if guard_dump.get("recommended_mitigations") or guard_dump.get("safety_and_privacy_risks") else None)
                )
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    agent_outputs["guardian"] = guard_dump
                    session.completed_agent_outputs["guardian"] = guard_dump
                    register_agent_result(state, "guardian", guard_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="guardian",
                            status="success",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "guardian",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                    })
                    await self._emit_agent(req_id, "guardian", "completed", duration_ms=duration_ms)
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="guardian",
                            status="failed",
                            error="Guardian returned failed status",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "guardian",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                        "error": "Guardian returned failed status",
                    })
                    await self._emit_agent(
                        req_id,
                        "guardian",
                        "failed",
                        duration_ms=duration_ms,
                        error="Guardian returned failed status",
                    )
            except Exception as e:
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                logger.error(f"Guardian execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="guardian",
                        status="failed",
                        error=str(e),
                        duration_ms=duration_ms,
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "guardian",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                await self._emit_agent(req_id, "guardian", "failed", duration_ms=duration_ms, error=str(e))

        # 5. Security
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        security_findings = None
        if "security" in selected_agents:
            t0 = time.monotonic()
            await self._emit_agent(req_id, "security", "running")
            context_for_sec = {
                "engineer": agent_outputs.get("engineer"),
                "researcher": agent_outputs.get("researcher"),
                "strategist": agent_outputs.get("strategist"),
            }
            try:
                try:
                    sec_output = await self.security.run(
                        problem=request.problem,
                        engineering=agent_outputs.get("engineer"),
                        research=agent_outputs.get("researcher"),
                        strategy=agent_outputs.get("strategist"),
                        context=context_for_sec,
                        domain=resolved_domain,
                    )
                except TypeError:
                    try:
                        sec_output = await self.security.run(request.problem, context=context_for_sec, domain=resolved_domain)
                    except TypeError:
                        sec_output = await self.security.run(request.problem, context=context_for_sec)

                sec_dump = sec_output.model_dump() if hasattr(sec_output, "model_dump") else dict(sec_output)
                status_val = getattr(sec_output, "status", None) or sec_dump.get("status")
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                if str(status_val).lower() in ("completed", "success"):
                    agent_outputs["security"] = sec_dump
                    session.completed_agent_outputs["security"] = sec_dump
                    security_findings = sec_dump
                    register_agent_result(state, "security", sec_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="security",
                            status="success",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "security",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                    })
                    await self._emit_agent(req_id, "security", "completed", duration_ms=duration_ms)
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="security",
                            status="failed",
                            error="Security returned failed status",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "security",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                        "error": "Security returned failed status",
                    })
                    await self._emit_agent(
                        req_id,
                        "security",
                        "failed",
                        duration_ms=duration_ms,
                        error="Security returned failed status",
                    )
            except Exception as e:
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                logger.error(f"Security execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="security",
                        status="failed",
                        error=str(e),
                        duration_ms=duration_ms,
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "security",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                await self._emit_agent(req_id, "security", "failed", duration_ms=duration_ms, error=str(e))

        # 6. Evaluator
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        evaluation_findings = None
        detected_conflicts: List[str] = []
        if "evaluator" in selected_agents:
            t0 = time.monotonic()
            await self._emit_agent(req_id, "evaluator", "running")
            context_for_eval = {"all_outputs": agent_outputs}
            try:
                try:
                    eval_output = await self.evaluator.run(request.problem, context=context_for_eval, domain=resolved_domain)
                except TypeError:
                    try:
                        eval_output = await self.evaluator.run(request.problem, context=context_for_eval)
                    except TypeError:
                        try:
                            eval_output = await self.evaluator.run(request.problem, domain=resolved_domain)
                        except TypeError:
                            eval_output = await self.evaluator.run(request.problem)

                eval_dump = eval_output.model_dump() if hasattr(eval_output, "model_dump") else dict(eval_output)
                status_val = (
                    getattr(eval_output, "status", None)
                    or eval_dump.get("status")
                    or (eval_dump.get("evaluator_result") or {}).get("status")
                )
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    agent_outputs["evaluator"] = eval_dump
                    session.completed_agent_outputs["evaluator"] = eval_dump
                    evaluation_findings = eval_dump
                    register_agent_result(state, "evaluator", eval_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="evaluator",
                            status="success",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "evaluator",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                    })
                    await self._emit_agent(req_id, "evaluator", "completed", duration_ms=duration_ms)
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="evaluator",
                            status="failed",
                            error="Evaluator returned failed status",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "evaluator",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                        "error": "Evaluator returned failed status",
                    })
                    await self._emit_agent(
                        req_id,
                        "evaluator",
                        "failed",
                        duration_ms=duration_ms,
                        error="Evaluator returned failed status",
                    )
                detected_conflicts = getattr(eval_output, "detected_contradictions", []) or eval_dump.get("detected_contradictions", [])
            except Exception as e:
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                logger.error(f"Evaluator execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="evaluator",
                        status="failed",
                        error=str(e),
                        duration_ms=duration_ms,
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "evaluator",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                await self._emit_agent(req_id, "evaluator", "failed", duration_ms=duration_ms, error=str(e))

        # 7. Conflict Resolver
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        if "conflict_resolver" in selected_agents:
            t0 = time.monotonic()
            await self._emit_agent(req_id, "conflict_resolver", "running")
            context_for_cr = {"all_outputs": agent_outputs}
            try:
                try:
                    cr_output = await self.conflict_resolver.run(request.problem, context=context_for_cr, domain=resolved_domain)
                except TypeError:
                    try:
                        cr_output = await self.conflict_resolver.run(request.problem, context=context_for_cr)
                    except TypeError:
                        try:
                            cr_output = await self.conflict_resolver.run(request.problem, domain=resolved_domain)
                        except TypeError:
                            cr_output = await self.conflict_resolver.run(request.problem)

                cr_dump = cr_output.model_dump() if hasattr(cr_output, "model_dump") else dict(cr_output)
                agent_outputs["conflict_resolver"] = cr_dump
                session.completed_agent_outputs["conflict_resolver"] = cr_dump
                register_agent_result(state, "conflict_resolver", cr_output)
                status_val = getattr(cr_output, "status", None) or cr_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="conflict_resolver",
                            status="success",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "conflict_resolver",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                    })
                    await self._emit_agent(req_id, "conflict_resolver", "completed", duration_ms=duration_ms)
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="conflict_resolver",
                            status="failed",
                            error="Conflict Resolver returned failed status",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "conflict_resolver",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                        "error": "Conflict Resolver returned failed status",
                    })
                    await self._emit_agent(
                        req_id,
                        "conflict_resolver",
                        "failed",
                        duration_ms=duration_ms,
                        error="Conflict Resolver returned failed status",
                    )
            except Exception as e:
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                logger.error(f"Conflict Resolver execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="conflict_resolver",
                        status="failed",
                        error=str(e),
                        duration_ms=duration_ms,
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "conflict_resolver",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                await self._emit_agent(req_id, "conflict_resolver", "failed", duration_ms=duration_ms, error=str(e))

        # 8. Synthesizer
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        final_answer = ""
        should_run_synth = (request.selected_agents is None) or ("synthesizer" in selected_agents)
        if should_run_synth:
            t0 = time.monotonic()
            await self._emit_agent(req_id, "synthesizer", "running")
            context_for_synth = {
                "all_outputs": agent_outputs,
                "execution_statuses": execution_statuses,
                "acquired_information": acquired_info,
                "retrieved_sources": retrieved_sources,
                "domain": resolved_domain,
            }
            try:
                if hasattr(self.synthesizer, "synthesize"):
                    try:
                        synth_output = await self.synthesizer.synthesize(request.problem, context=context_for_synth, domain=resolved_domain)
                    except TypeError:
                        synth_output = await self.synthesizer.synthesize(request.problem, context=context_for_synth)
                else:
                    try:
                        synth_output = await self.synthesizer.run(request.problem, context=context_for_synth, domain=resolved_domain)
                    except TypeError:
                        try:
                            synth_output = await self.synthesizer.run(request.problem, context=context_for_synth)
                        except TypeError:
                            synth_output = await self.synthesizer.run(request.problem)

                synth_dump = synth_output.model_dump() if hasattr(synth_output, "model_dump") else dict(synth_output)
                agent_outputs["synthesizer"] = synth_dump
                session.completed_agent_outputs["synthesizer"] = synth_dump
                register_agent_result(state, "synthesizer", synth_output)
                status_val = getattr(synth_output, "status", None) or synth_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    if "synthesizer" in selected_agents:
                        execution_statuses.append(
                            AgentExecutionStatus(
                                agent_name="synthesizer",
                                status="success",
                                duration_ms=duration_ms,
                                timestamp=_iso_now(),
                            )
                        )
                    execution_trace.append({
                        "agent": "synthesizer",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                    })
                    final_answer = synth_dump.get("final_answer") or synth_dump.get("final_text") or synth_dump.get("reconciled_solution") or ""
                    await self._emit_agent(req_id, "synthesizer", "completed", duration_ms=duration_ms)
                else:
                    synth_err = synth_dump.get("error") or "Synthesizer returned failed status"
                    if "synthesizer" in selected_agents:
                        execution_statuses.append(
                            AgentExecutionStatus(
                                agent_name="synthesizer",
                                status="failed",
                                error=synth_err,
                                duration_ms=duration_ms,
                                timestamp=_iso_now(),
                            )
                        )
                    execution_trace.append({
                        "agent": "synthesizer",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                        "error": synth_err,
                    })
                    final_answer = (
                        "CHAI could not complete the final synthesis reliably for this request.\n\n"
                        "Some specialist analysis was completed, but the final synthesis stage failed. "
                        "The result has therefore been withheld rather than presenting an unverified answer."
                    )
                    await self._emit_agent(req_id, "synthesizer", "failed", duration_ms=duration_ms, error=synth_err)
            except Exception as e:
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                logger.error(f"Synthesizer execution error: {e}")
                if "synthesizer" in selected_agents:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="synthesizer",
                            status="failed",
                            error=str(e),
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                execution_trace.append({
                    "agent": "synthesizer",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                final_answer = (
                    "CHAI could not complete the final synthesis reliably for this request.\n\n"
                    "Some specialist analysis was completed, but the final synthesis stage failed. "
                    "The result has therefore been withheld rather than presenting an unverified answer."
                )
                await self._emit_agent(req_id, "synthesizer", "failed", duration_ms=duration_ms, error=str(e))
        else:
            if not selected_agents:
                final_answer = f"Direct response provided for: {request.problem}"
            else:
                final_answer = "Based on the comprehensive analysis of our specialized agents:\n"
            if "strategist" in agent_outputs:
                st = agent_outputs["strategist"]
                strat_txt = st.get("strategy") or st.get("strategy_overview", "")
                if strat_txt:
                    final_answer += f"\nStrategy:\n{strat_txt}\n"
            if "engineer" in agent_outputs:
                eng = agent_outputs["engineer"]
                eng_txt = eng.get("technical_architecture") or eng.get("architecture_overview", "")
                if eng_txt:
                    final_answer += f"\nArchitecture:\n{eng_txt}\n"
            if "security" in agent_outputs:
                sec_txt = agent_outputs["security"].get("security_summary", "")
                if sec_txt:
                    final_answer += f"\nSecurity:\n{sec_txt}\n"
            if "guardian" in agent_outputs:
                g = agent_outputs["guardian"]
                guard_txt = g.get("recommended_mitigations") or (g.get("guardian_result") or {}).get("safety_assessment") or g.get("safety_assessment", "")
                if guard_txt:
                    final_answer += f"\nSafety:\n{guard_txt}\n"
            if "evaluator" in agent_outputs:
                ev = agent_outputs["evaluator"]
                eval_txt = ev.get("overall_assessment", "") or (ev.get("evaluator_result") or {}).get("overall_assessment", "")
                if eval_txt:
                    final_answer += f"\nEvaluation:\n{eval_txt}\n"
            if "conflict_resolver" in agent_outputs:
                cr_resolutions = agent_outputs["conflict_resolver"].get("resolutions", [])
                if cr_resolutions:
                    final_answer += "\nConflict Resolutions:\n"
                    for r in cr_resolutions:
                        desc = r.get("conflict", "")
                        pref = r.get("preferred_option", "")
                        reason = r.get("reason", "")
                        final_answer += f"- {desc}: Prefer {pref}. {reason}\n"

        if request.selected_agents is None and final_answer:
            synth_is_success = (val_str.lower() in ("completed", "success") or "completed" in val_str.lower()) if should_run_synth else True
            if synth_is_success and not final_answer.startswith("Based on the comprehensive analysis") and not final_answer.startswith("CHAI could not"):
                final_answer = f"Based on the comprehensive analysis of our specialized agents:\n\n{final_answer}"

        if "synthesizer" not in agent_outputs and final_answer:
            agent_outputs["synthesizer"] = {
                "agent": "synthesizer",
                "status": "completed",
                "final_answer": final_answer,
            }

        # 9. Reliability Monitor
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        rm_action: Optional[ReliabilityAction] = None
        rm_dump: Dict[str, Any] = {}
        if "reliability_monitor" in selected_agents:
            t0 = time.monotonic()
            await self._emit_agent(req_id, "reliability_monitor", "running")
            context_for_rm = {
                "all_outputs": agent_outputs,
                "final_answer": final_answer,
                "execution_statuses": execution_statuses,
                "domain": resolved_domain,
            }
            try:
                try:
                    rm_output = await self.reliability_monitor.run(request.problem, context=context_for_rm, domain=resolved_domain)
                except TypeError:
                    try:
                        rm_output = await self.reliability_monitor.run(request.problem, context=context_for_rm)
                    except TypeError:
                        try:
                            rm_output = await self.reliability_monitor.run(request.problem, domain=resolved_domain)
                        except TypeError:
                            rm_output = await self.reliability_monitor.run(request.problem)

                rm_dump = rm_output.model_dump() if hasattr(rm_output, "model_dump") else dict(rm_output)
                agent_outputs["reliability_monitor"] = rm_dump
                session.completed_agent_outputs["reliability_monitor"] = rm_dump
                register_agent_result(state, "reliability_monitor", rm_output)
                status_val = getattr(rm_output, "status", None) or rm_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="reliability_monitor",
                            status="success",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "reliability_monitor",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                    })
                    await self._emit_agent(req_id, "reliability_monitor", "completed", duration_ms=duration_ms)
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="reliability_monitor",
                            status="failed",
                            error="Reliability Monitor returned failed status",
                            duration_ms=duration_ms,
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "reliability_monitor",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": duration_ms,
                        "error": "Reliability Monitor returned failed status",
                    })
                    await self._emit_agent(
                        req_id,
                        "reliability_monitor",
                        "failed",
                        duration_ms=duration_ms,
                        error="Reliability Monitor returned failed status",
                    )

                raw_action = getattr(rm_output, "action", None) or rm_dump.get("action")
                if isinstance(raw_action, ReliabilityAction):
                    rm_action = raw_action
                elif isinstance(raw_action, str):
                    try:
                        rm_action = ReliabilityAction(raw_action.upper())
                    except Exception:
                        rm_action = ReliabilityAction.PROCEED_WITH_LIMITATIONS
            except Exception as e:
                duration_ms = round((time.monotonic() - t0) * 1000, 2)
                logger.error(f"Reliability Monitor execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="reliability_monitor",
                        status="failed",
                        error=str(e),
                        duration_ms=duration_ms,
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "reliability_monitor",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": duration_ms,
                    "error": str(e),
                })
                await self._emit_agent(req_id, "reliability_monitor", "failed", duration_ms=duration_ms, error=str(e))
                failed_rm = ReliabilityMonitorAgent._make_failed_output(f"Execution error: {e}")
                rm_dump = failed_rm.model_dump()
                agent_outputs["reliability_monitor"] = rm_dump
                session.completed_agent_outputs["reliability_monitor"] = rm_dump
                rm_action = failed_rm.action

        # Downstream reasoning-quality gate enforcement
        delivered_answer = final_answer
        gate_blocked = False
        gate_requested_info = False

        if rm_action == ReliabilityAction.BLOCK_OUTPUT:
            gate_blocked = True
            reasons = rm_dump.get("concerns", []) or ["Critical reliability or safety standard violation."]
            reasons_str = "; ".join(reasons) if isinstance(reasons, list) else str(reasons)
            delivered_answer = (
                f"[BLOCKED] The synthesized output cannot be delivered because it failed critical "
                f"reliability and safety standards. Reason: {reasons_str}"
            )
        elif rm_action == ReliabilityAction.REQUEST_MORE_INFORMATION:
            gate_requested_info = True
            missing_items = rm_dump.get("missing_information", []) or []
            if missing_items:
                items_str = "\n".join(f"- {item}" for item in missing_items)
                delivered_answer = (
                    f"Additional information is required before a complete recommendation can be provided.\n\n"
                    f"Missing Information:\n{items_str}\n\n"
                    f"Please provide the details above to proceed."
                )
            else:
                delivered_answer = (
                    "Additional information is required before a complete recommendation can be provided. "
                    "Please provide further details regarding the problem requirements."
                )
        elif rm_action in (ReliabilityAction.PROCEED_WITH_LIMITATIONS, ReliabilityAction.PROCEED):
            delivered_answer = final_answer

        # Collect sources from researcher
        res_raw_sources = agent_outputs.get("researcher", {}).get("sources", []) or agent_outputs.get("researcher", {}).get("source_references", [])
        for s in res_raw_sources:
            if isinstance(s, dict):
                src = s.get("title") or s.get("url") or str(s)
            elif isinstance(s, str):
                src = s
            elif hasattr(s, "title"):
                src = s.title
            else:
                src = str(s)
            if src and src not in retrieved_sources:
                retrieved_sources.append(src)

        # Collect limitations from guardian
        limitations = list(
            agent_outputs.get("guardian", {}).get("limitations")
            or agent_outputs.get("guardian", {}).get("safety_risks")
            or []
        )

        # Attach Reliability Monitor limitations/concerns
        if "reliability_monitor" in agent_outputs:
            rm_data = agent_outputs["reliability_monitor"]
            rm_extras = (
                rm_data.get("limitations", [])
                + rm_data.get("concerns", [])
                + rm_data.get("evidence_gaps", [])
                + rm_data.get("unresolved_conflicts", [])
                + rm_data.get("missing_information", [])
            )
            for item in rm_extras:
                if item and str(item).strip() and str(item).strip() not in limitations:
                    limitations.append(str(item).strip())

        # 10. Output Validator (Structural & Operational Output Gate)
        cancelled_res = await _check_or_cancel()
        if cancelled_res:
            return cancelled_res
        t0 = time.monotonic()
        await self._emit_agent(req_id, "output_validator", "running")
        try:
            try:
                validation_result = self.output_validator.validate(
                    delivered_answer,
                    context={"all_outputs": agent_outputs, "selected_agents": selected_agents},
                    domain=resolved_domain,
                )
            except TypeError:
                validation_result = self.output_validator.validate(
                    delivered_answer,
                    context={"all_outputs": agent_outputs, "selected_agents": selected_agents},
                )
            duration_ms = round((time.monotonic() - t0) * 1000, 2)
            execution_trace.append({
                "agent": "output_validator",
                "status": "completed",
                "timestamp": _iso_now(),
                "duration_ms": duration_ms,
            })
        except Exception as val_err:
            duration_ms = round((time.monotonic() - t0) * 1000, 2)
            logger.error(f"Output Validator execution error: {val_err}")
            validation_result = OutputValidationResult(
                agent="output_validator",
                status="failed",
                is_valid=False,
                errors=[f"Output Validator execution failure: {val_err}"],
                sanitized_output=None,
            )
            execution_trace.append({
                "agent": "output_validator",
                "status": "failed",
                "timestamp": _iso_now(),
                "duration_ms": duration_ms,
                "error": str(val_err),
            })

        dumped_val = validation_result.model_dump() if hasattr(validation_result, "model_dump") else dict(validation_result)
        agent_outputs["output_validator"] = dumped_val
        session.completed_agent_outputs["output_validator"] = dumped_val
        register_agent_result(state, "output_validator", validation_result)

        if execution_event_manager.is_cancelled(req_id):
            return self._build_cancelled_response(
                request=request,
                req_id=req_id,
                agent_outputs=agent_outputs,
                execution_statuses=execution_statuses,
                execution_trace=execution_trace,
                selected_agents=selected_agents,
                retrieved_sources=retrieved_sources,
                acquired_info=acquired_info,
                domain_category=domain_category,
                resolved_domain=resolved_domain,
            )

        is_valid_val = getattr(validation_result, "is_valid", getattr(validation_result, "valid", True))
        val_errors = getattr(validation_result, "errors", getattr(validation_result, "issues", [])) or []
        sanitized_output_val = getattr(validation_result, "sanitized_output", None) or getattr(validation_result, "sanitized_text", None)

        if is_valid_val:
            final_deliverable = sanitized_output_val or delivered_answer
            await self._emit_agent(req_id, "output_validator", "completed", duration_ms=duration_ms)
        else:
            logger.warning(f"Output validation failed: {val_errors}")
            err_reasons = "; ".join(val_errors) if val_errors else "Structural or operational validation failure"
            await self._emit_agent(req_id, "output_validator", "failed", duration_ms=duration_ms, error=err_reasons)
            if any("Internal agent failure" in e for e in val_errors):
                final_deliverable = (
                    "CHAI could not complete the final synthesis reliably for this request.\n\n"
                    "Some specialist analysis was completed, but the final synthesis stage failed. "
                    "The result has therefore been withheld rather than presenting an unverified answer."
                )
            else:
                final_deliverable = (
                    f"[DELIVERY BLOCKED] The generated response failed final delivery validation and cannot be delivered. "
                    f"Validation findings: {err_reasons}"
                )

        # Determine overall request status semantics
        total_count = len(selected_agents) if selected_agents else 0
        success_count = sum(1 for s in execution_statuses if s.status.lower() in ("success", "completed"))
        failure_count = sum(1 for s in execution_statuses if s.status.lower() in ("failed", "failure", "error"))

        if not is_valid_val or (total_count > 0 and failure_count == total_count):
            overall_request_status = "failed"
        elif gate_blocked:
            overall_request_status = "blocked"
        elif gate_requested_info:
            overall_request_status = "requires_information"
        elif not selected_agents:
            overall_request_status = "completed"
        else:
            total_count = len(selected_agents)
            success_count = sum(1 for s in execution_statuses if s.status.lower() in ("success", "completed"))
            failure_count = sum(1 for s in execution_statuses if s.status.lower() in ("failed", "failure", "error"))

            if success_count == total_count:
                overall_request_status = "completed"
            elif success_count > 0 and failure_count > 0:
                overall_request_status = "partial"
            elif failure_count == total_count or success_count == 0:
                overall_request_status = "failed"
            else:
                overall_request_status = "partial" if success_count > 0 else "failed"

        # Determine agent_outputs representation
        if request.selected_agents is None:
            # Output only the agents that were actually selected and executed
            final_agent_outputs = {k: v for k, v in agent_outputs.items() if k in selected_agents}
        else:
            # When specific agents are requested, preserve all executed outputs
            final_agent_outputs = agent_outputs

        user_facing_deliverable = format_user_facing_response(
            query=request.problem,
            raw_answer=final_deliverable,
            route=route,
            domain=route_decision.domain if route_decision else "general",
            requested_depth=route_decision.requested_depth if route_decision else "normal",
            agent_outputs=final_agent_outputs,
            reliability_action=rm_action,
            validation_result=validation_result,
        )

        if conversation_id:
            try:
                from backend.memory.store import memory_store
                await memory_store.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="user",
                    content=request.problem,
                )
                await memory_store.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="assistant",
                    content=user_facing_deliverable,
                )
            except Exception as me:
                logger.debug(f"Could not persist conversation history: {me}")

        await execution_event_manager.emit(
            request_id=req_id,
            event="final_answer",
            status="completed" if overall_request_status in ("completed", "partial", "requires_information") else "failed",
            final_answer=user_facing_deliverable,
            message="Final answer delivered" if overall_request_status != "failed" else "Request completed with failures",
        )

        return FinalResponse(
            request_id=getattr(request, "request_id", None) or state.get("request_id"),
            conversation_id=conversation_id,
            request_status=overall_request_status,
            status=overall_request_status,
            route=route,
            complexity=complexity,
            selected_agents=selected_agents,
            agent_outputs=final_agent_outputs,
            retrieved_sources=retrieved_sources,
            acquired_information=acquired_info,
            agent_execution_statuses=execution_statuses,
            evaluation_findings=evaluation_findings,
            security_findings=security_findings,
            detected_conflicts=detected_conflicts,
            final_synthesized_answer=final_deliverable,
            final_answer=user_facing_deliverable,
            synthesis_result=agent_outputs.get("synthesizer"),
            validation_result=agent_outputs.get("output_validator"),
            execution_trace=execution_trace,
            errors=[s.error for s in execution_statuses if s.error],
            limitations=limitations,
            metadata={
                "selected_agents_count": len(selected_agents),
                "acquired_information_count": len(acquired_info),
            },
            domain_category=state.get("domain_category", domain_category),
            resolved_domain=state.get("resolved_domain") or normalize_domain(domain_category),
        )


# Backward-compatible alias
Coordinator = CHAICoordinator

__all__ = ["CHAICoordinator", "Coordinator", "CANONICAL_AGENTS"]
