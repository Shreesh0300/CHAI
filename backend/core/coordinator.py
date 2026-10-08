"""
Coordinator module for CHAI (Coordinated Hybrid Agentic Intelligence).
Orchestrates multi-agent execution across Information Acquisition,
domain specialist agents, Conflict Resolver, Synthesizer,
Reliability Monitor, and Output Validator.
"""
from datetime import datetime, timezone
import os
import time
from typing import Optional, Any, Dict, List, Set

from backend.core.schemas import (
    SolveRequest,
    FinalResponse,
    AgentExecutionStatus,
    CHAIExecutionResult,
)
from backend.core.state import (
    create_initial_state,
    CHAIState,
    register_agent_result,
    get_canonical_agent_result,
)
from backend.core.router import (
    route_request,
    is_simple_query,
    ROUTE_SIMPLE,
    ROUTE_COMPLEX,
)
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
from backend.shared.debug_observability import log_debug_agent_output
from backend.shared.logger import get_logger

logger = get_logger(__name__)

CANONICAL_AGENTS = ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"]


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

    async def process_request(self, request: SolveRequest) -> FinalResponse:
        """Executes a request through the coordinated multi-agent workflow."""
        logger.info(f"Coordinator: processing request: {request.problem}")

        agent_outputs: Dict[str, Any] = {}
        execution_statuses: List[AgentExecutionStatus] = []
        execution_trace: List[Dict[str, Any]] = []

        # Initialize canonical state tracking
        state = create_initial_state(
            problem=request.problem,
            user_id=getattr(request, "user_id", None),
            context=getattr(request, "context", None),
        )

        # -------------------------------------------------------------
        # Determine Route and Selected Agents
        # -------------------------------------------------------------
        if request.selected_agents is not None:
            selected_agents = [a.lower().strip() for a in request.selected_agents]
            route = "simple" if not selected_agents else "complex"
            complexity = "low" if not selected_agents else "high"
        elif is_simple_query(request.problem):
            selected_agents = []
            route = "simple"
            complexity = "low"
        else:
            route_decision = route_request(request.problem, getattr(request, "context", None))
            route = route_decision.route
            complexity = route_decision.complexity
            if route == "simple":
                selected_agents = []
            else:
                selected_agents = list(CANONICAL_AGENTS)

        execution_trace.append({
            "agent": "router",
            "status": "completed",
            "timestamp": _iso_now(),
            "duration_ms": 0.0,
            "route": route,
        })

        # -------------------------------------------------------------
        # Simple Direct Response Path (No specialized agents invoked)
        # -------------------------------------------------------------
        if route == "simple" or (request.selected_agents is not None and not selected_agents):
            direct_text = f"Direct response provided for: {request.problem}"
            log_debug_agent_output("final answer", direct_text)

            return FinalResponse(
                request_id=getattr(request, "request_id", None) or state.get("request_id"),
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
                final_synthesized_answer=direct_text,
                final_answer=direct_text,
                execution_trace=execution_trace,
                errors=[],
                limitations=[],
                metadata={"route": "simple"},
            )

        # -------------------------------------------------------------
        # Complex Multi-Agent Pipeline
        # -------------------------------------------------------------

        # 0. Information Acquisition
        acquired_info: List[Any] = []
        retrieved_sources: List[str] = []
        if self.information_acquisition and "researcher" in selected_agents:
            t0 = time.monotonic()
            try:
                info_res = await self.information_acquisition.acquire(request.problem)
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
                execution_trace.append({
                    "agent": "information_acquisition",
                    "status": "completed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "details": f"Acquired {len(acquired_info)} information items.",
                })
            except Exception as e:
                logger.warning(f"Information Acquisition execution error: {e}")
                execution_trace.append({
                    "agent": "information_acquisition",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "error": str(e),
                })

        # 1. Researcher
        researcher_fatal_stop = False
        if "researcher" in selected_agents:
            t0 = time.monotonic()
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
                    )
                except TypeError:
                    try:
                        res_output = await self.researcher.run(
                            request.problem,
                            context=context_val,
                        )
                    except TypeError:
                        res_output = await self.researcher.run(request.problem)

                res_dump = res_output.model_dump() if hasattr(res_output, "model_dump") else dict(res_output)
                status_val = getattr(res_output, "status", None) or res_dump.get("status")
                if str(status_val).lower() in ("completed", "success"):
                    agent_outputs["researcher"] = res_dump
                    register_agent_result(state, "researcher", res_output)
                    log_debug_agent_output("researcher output", res_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="researcher",
                            status="success",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "researcher",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    })
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="researcher",
                            status="failed",
                            error="Researcher returned failed status",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "researcher",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                        "error": "Researcher returned failed status",
                    })
            except Exception as e:
                if isinstance(e, RuntimeError):
                    researcher_fatal_stop = True
                logger.error(f"Researcher execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="researcher",
                        status="failed",
                        error=str(e),
                        duration_ms=round((time.monotonic() - t0) * 1000, 2),
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "researcher",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "error": str(e),
                })

        # Hard-stop on Researcher fatal failure during complex pipeline execution
        if researcher_fatal_stop:
            if request.selected_agents is None:
                err_text = "Researcher agent failed. Unable to continue the requested analysis."
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
        if "strategist" in selected_agents:
            t0 = time.monotonic()
            research_data = agent_outputs.get("researcher", {})
            context_for_strat = {"researcher_output": research_data, "researcher": research_data}
            try:
                try:
                    strat_output = await self.strategist.run(
                        problem=request.problem,
                        research=research_data,
                        context=context_for_strat,
                    )
                except TypeError:
                    strat_output = await self.strategist.run(request.problem)

                strat_dump = strat_output.model_dump() if hasattr(strat_output, "model_dump") else dict(strat_output)
                status_val = getattr(strat_output, "status", None) or strat_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                if val_str.lower() not in ("failed", "error"):
                    agent_outputs["strategist"] = strat_dump
                    try:
                        register_agent_result(state, "strategist", strat_output)
                    except Exception:
                        pass
                    log_debug_agent_output("strategist output", strat_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="strategist",
                            status="success",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "strategist",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    })
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="strategist",
                            status="failed",
                            error="Strategist returned failed status",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "strategist",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                        "error": "Strategist returned failed status",
                    })
            except Exception as e:
                logger.error(f"Strategist execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="strategist",
                        status="failed",
                        error=str(e),
                        duration_ms=round((time.monotonic() - t0) * 1000, 2),
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "strategist",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "error": str(e),
                })

        # 3. Engineer
        if "engineer" in selected_agents:
            t0 = time.monotonic()
            context_for_eng = {
                "researcher": agent_outputs.get("researcher"),
                "strategist": agent_outputs.get("strategist"),
            }
            try:
                try:
                    eng_output = await self.engineer.run(request.problem, context=context_for_eng)
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
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    agent_outputs["engineer"] = eng_dump
                    register_agent_result(state, "engineer", eng_output)
                    log_debug_agent_output("engineer output", eng_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="engineer",
                            status="success",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "engineer",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    })
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="engineer",
                            status="failed",
                            error="Engineer returned failed status",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "engineer",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                        "error": "Engineer returned failed status",
                    })
            except Exception as e:
                logger.error(f"Engineer execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="engineer",
                        status="failed",
                        error=str(e),
                        duration_ms=round((time.monotonic() - t0) * 1000, 2),
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "engineer",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "error": str(e),
                })

        # 4. Guardian
        if "guardian" in selected_agents:
            t0 = time.monotonic()
            context_for_guard = {
                "engineer": agent_outputs.get("engineer"),
                "strategist": agent_outputs.get("strategist"),
                "researcher": agent_outputs.get("researcher"),
            }
            try:
                try:
                    guard_output = await self.guardian.run(request.problem, context=context_for_guard)
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
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    agent_outputs["guardian"] = guard_dump
                    register_agent_result(state, "guardian", guard_output)
                    log_debug_agent_output("guardian output", guard_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="guardian",
                            status="success",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "guardian",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    })
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="guardian",
                            status="failed",
                            error="Guardian returned failed status",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "guardian",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                        "error": "Guardian returned failed status",
                    })
            except Exception as e:
                logger.error(f"Guardian execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="guardian",
                        status="failed",
                        error=str(e),
                        duration_ms=round((time.monotonic() - t0) * 1000, 2),
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "guardian",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "error": str(e),
                })

        # 5. Security
        security_findings = None
        if "security" in selected_agents:
            t0 = time.monotonic()
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
                    )
                except TypeError:
                    sec_output = await self.security.run(request.problem, context=context_for_sec)

                sec_dump = sec_output.model_dump() if hasattr(sec_output, "model_dump") else dict(sec_output)
                status_val = getattr(sec_output, "status", None) or sec_dump.get("status")
                if str(status_val).lower() in ("completed", "success"):
                    agent_outputs["security"] = sec_dump
                    security_findings = sec_dump
                    register_agent_result(state, "security", sec_output)
                    log_debug_agent_output("security output", sec_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="security",
                            status="success",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "security",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    })
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="security",
                            status="failed",
                            error="Security returned failed status",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "security",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                        "error": "Security returned failed status",
                    })
            except Exception as e:
                logger.error(f"Security execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="security",
                        status="failed",
                        error=str(e),
                        duration_ms=round((time.monotonic() - t0) * 1000, 2),
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "security",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "error": str(e),
                })

        # 6. Evaluator
        evaluation_findings = None
        detected_conflicts: List[str] = []
        if "evaluator" in selected_agents:
            t0 = time.monotonic()
            context_for_eval = {"all_outputs": agent_outputs}
            try:
                try:
                    eval_output = await self.evaluator.run(request.problem, context=context_for_eval)
                except TypeError:
                    eval_output = await self.evaluator.run(request.problem)

                eval_dump = eval_output.model_dump() if hasattr(eval_output, "model_dump") else dict(eval_output)
                status_val = (
                    getattr(eval_output, "status", None)
                    or eval_dump.get("status")
                    or (eval_dump.get("evaluator_result") or {}).get("status")
                )
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                if val_str.lower() in ("completed", "success", "partial") or "completed" in val_str.lower() or "partial" in val_str.lower():
                    agent_outputs["evaluator"] = eval_dump
                    evaluation_findings = eval_dump
                    register_agent_result(state, "evaluator", eval_output)
                    log_debug_agent_output("evaluator output", eval_output)
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="evaluator",
                            status="success",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "evaluator",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    })
                else:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="evaluator",
                            status="failed",
                            error="Evaluator returned failed status",
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                    execution_trace.append({
                        "agent": "evaluator",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                        "error": "Evaluator returned failed status",
                    })
                detected_conflicts = getattr(eval_output, "detected_contradictions", []) or eval_dump.get("detected_contradictions", [])
            except Exception as e:
                logger.error(f"Evaluator execution error: {e}")
                execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name="evaluator",
                        status="failed",
                        error=str(e),
                        duration_ms=round((time.monotonic() - t0) * 1000, 2),
                        timestamp=_iso_now(),
                    )
                )
                execution_trace.append({
                    "agent": "evaluator",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "error": str(e),
                })

        # 7. Conflict Resolver
        should_run_cr = (request.selected_agents is None) or ("conflict_resolver" in selected_agents)
        if should_run_cr:
            t0 = time.monotonic()
            context_for_cr = {
                "all_outputs": agent_outputs,
                "failed_agents": [s.agent_name for s in execution_statuses if s.status.lower() in ("failed", "error")],
                "execution_statuses": [s.model_dump() for s in execution_statuses],
            }
            try:
                try:
                    cr_output = await self.conflict_resolver.run(request.problem, context=context_for_cr)
                except TypeError:
                    cr_output = await self.conflict_resolver.run(request.problem)

                cr_dump = cr_output.model_dump() if hasattr(cr_output, "model_dump") else dict(cr_output)
                agent_outputs["conflict_resolver"] = cr_dump
                status_val = getattr(cr_output, "status", None) or cr_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                log_debug_agent_output("conflict resolver output", cr_output)
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    if "conflict_resolver" in selected_agents:
                        execution_statuses.append(
                            AgentExecutionStatus(
                                agent_name="conflict_resolver",
                                status="success",
                                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                                timestamp=_iso_now(),
                            )
                        )
                    execution_trace.append({
                        "agent": "conflict_resolver",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    })
                else:
                    if "conflict_resolver" in selected_agents:
                        execution_statuses.append(
                            AgentExecutionStatus(
                                agent_name="conflict_resolver",
                                status="failed",
                                error="Conflict Resolver returned failed status",
                                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                                timestamp=_iso_now(),
                            )
                        )
                    execution_trace.append({
                        "agent": "conflict_resolver",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                        "error": "Conflict Resolver returned failed status",
                    })
            except Exception as e:
                logger.error(f"Conflict Resolver execution error: {e}")
                if "conflict_resolver" in selected_agents:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="conflict_resolver",
                            status="failed",
                            error=str(e),
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                execution_trace.append({
                    "agent": "conflict_resolver",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "error": str(e),
                })

        # 8. Synthesizer
        final_answer = ""
        should_run_synth = (request.selected_agents is None) or ("synthesizer" in selected_agents)
        if should_run_synth:
            t0 = time.monotonic()
            context_for_synth = {
                "all_outputs": agent_outputs,
                "execution_statuses": execution_statuses,
                "failed_agents": [s.agent_name for s in execution_statuses if s.status.lower() in ("failed", "error")],
            }
            log_debug_agent_output("synthesizer input", context_for_synth)
            try:
                if hasattr(self.synthesizer, "synthesize"):
                    synth_output = await self.synthesizer.synthesize(request.problem, context=context_for_synth)
                else:
                    try:
                        synth_output = await self.synthesizer.run(request.problem, context=context_for_synth)
                    except TypeError:
                        synth_output = await self.synthesizer.run(request.problem)

                synth_dump = synth_output.model_dump() if hasattr(synth_output, "model_dump") else dict(synth_output)
                agent_outputs["synthesizer"] = synth_dump
                register_agent_result(state, "synthesizer", synth_output)
                status_val = getattr(synth_output, "status", None) or synth_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    if "synthesizer" in selected_agents:
                        execution_statuses.append(
                            AgentExecutionStatus(
                                agent_name="synthesizer",
                                status="success",
                                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                                timestamp=_iso_now(),
                            )
                        )
                else:
                    if "synthesizer" in selected_agents:
                        execution_statuses.append(
                            AgentExecutionStatus(
                                agent_name="synthesizer",
                                status="failed",
                                error="Synthesizer returned failed status",
                                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                                timestamp=_iso_now(),
                            )
                        )
                execution_trace.append({
                    "agent": "synthesizer",
                    "status": "completed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                })
                final_answer = synth_dump.get("final_answer") or synth_dump.get("final_text") or synth_dump.get("reconciled_solution") or ""
            except Exception as e:
                logger.error(f"Synthesizer execution error: {e}")
                if "synthesizer" in selected_agents:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="synthesizer",
                            status="failed",
                            error=str(e),
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                execution_trace.append({
                    "agent": "synthesizer",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "error": str(e),
                })
                final_answer = ""
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
            if not final_answer.startswith("Based on the comprehensive analysis"):
                final_answer = f"Based on the comprehensive analysis of our specialized agents:\n\n{final_answer}"

        if "synthesizer" not in agent_outputs and final_answer:
            agent_outputs["synthesizer"] = {
                "agent": "synthesizer",
                "status": "completed",
                "final_answer": final_answer,
            }

        # 9. Reliability Monitor
        rm_action: Optional[ReliabilityAction] = None
        rm_dump: Dict[str, Any] = {}
        should_run_rm = (request.selected_agents is None) or ("reliability_monitor" in selected_agents)
        if should_run_rm:
            t0 = time.monotonic()
            context_for_rm = {
                "all_outputs": agent_outputs,
                "final_answer": final_answer,
                "execution_statuses": execution_statuses,
                "failed_agents": [s.agent_name for s in execution_statuses if s.status.lower() in ("failed", "error")],
            }
            try:
                try:
                    rm_output = await self.reliability_monitor.run(request.problem, context=context_for_rm)
                except TypeError:
                    rm_output = await self.reliability_monitor.run(request.problem)

                rm_dump = rm_output.model_dump() if hasattr(rm_output, "model_dump") else dict(rm_output)
                agent_outputs["reliability_monitor"] = rm_dump
                status_val = getattr(rm_output, "status", None) or rm_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    log_debug_agent_output("reliability monitor output", rm_output)
                    if "reliability_monitor" in selected_agents:
                        execution_statuses.append(
                            AgentExecutionStatus(
                                agent_name="reliability_monitor",
                                status="success",
                                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                                timestamp=_iso_now(),
                            )
                        )
                    execution_trace.append({
                        "agent": "reliability_monitor",
                        "status": "completed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    })
                else:
                    if "reliability_monitor" in selected_agents:
                        execution_statuses.append(
                            AgentExecutionStatus(
                                agent_name="reliability_monitor",
                                status="failed",
                                error="Reliability Monitor returned failed status",
                                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                                timestamp=_iso_now(),
                            )
                        )
                    execution_trace.append({
                        "agent": "reliability_monitor",
                        "status": "failed",
                        "timestamp": _iso_now(),
                        "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                        "error": "Reliability Monitor returned failed status",
                    })

                raw_action = getattr(rm_output, "action", None) or rm_dump.get("action")
                if isinstance(raw_action, ReliabilityAction):
                    rm_action = raw_action
                elif isinstance(raw_action, str):
                    try:
                        rm_action = ReliabilityAction(raw_action.upper())
                    except Exception:
                        rm_action = ReliabilityAction.PROCEED_WITH_LIMITATIONS
            except Exception as e:
                logger.error(f"Reliability Monitor execution error: {e}")
                if "reliability_monitor" in selected_agents:
                    execution_statuses.append(
                        AgentExecutionStatus(
                            agent_name="reliability_monitor",
                            status="failed",
                            error=str(e),
                            duration_ms=round((time.monotonic() - t0) * 1000, 2),
                            timestamp=_iso_now(),
                        )
                    )
                execution_trace.append({
                    "agent": "reliability_monitor",
                    "status": "failed",
                    "timestamp": _iso_now(),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                    "error": str(e),
                })
                failed_rm = ReliabilityMonitorAgent._make_failed_output(f"Execution error: {e}")
                rm_dump = failed_rm.model_dump()
                agent_outputs["reliability_monitor"] = rm_dump
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
                    f"Additional information is required before a completed answer can be provided.\n\n"
                    f"Missing Information:\n{items_str}\n\n"
                    f"Please provide the details above to proceed."
                )
            else:
                delivered_answer = (
                    "Additional information is required before a completed answer can be provided. "
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
        t0 = time.monotonic()
        failed_agents = [s.agent_name for s in execution_statuses if s.status.lower() in ("failed", "failure", "error")]
        completed_agents = [s.agent_name for s in execution_statuses if s.status.lower() in ("success", "completed")]

        try:
            validation_result = self.output_validator.validate(
                delivered_answer,
                context={
                    "all_outputs": agent_outputs,
                    "selected_agents": selected_agents,
                    "failed_agents": failed_agents,
                    "execution_statuses": [s.model_dump() for s in execution_statuses],
                },
            )
            execution_trace.append({
                "agent": "output_validator",
                "status": "completed",
                "timestamp": _iso_now(),
                "duration_ms": round((time.monotonic() - t0) * 1000, 2),
            })
        except Exception as val_err:
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
                "duration_ms": round((time.monotonic() - t0) * 1000, 2),
                "error": str(val_err),
            })

        dumped_val = validation_result.model_dump() if hasattr(validation_result, "model_dump") else dict(validation_result)
        agent_outputs["output_validator"] = dumped_val
        register_agent_result(state, "output_validator", validation_result)

        is_valid_val = getattr(validation_result, "is_valid", getattr(validation_result, "valid", True))
        val_errors = getattr(validation_result, "errors", getattr(validation_result, "issues", [])) or []
        sanitized_output_val = getattr(validation_result, "sanitized_output", None) or getattr(validation_result, "sanitized_text", None)

        if is_valid_val:
            final_deliverable = sanitized_output_val or delivered_answer
        else:
            logger.warning(f"Output validation failed: {val_errors}")
            err_reasons = "; ".join(val_errors) if val_errors else "Structural or operational validation failure"
            final_deliverable = (
                f"[DELIVERY BLOCKED] The generated response failed final delivery validation and cannot be delivered. "
                f"Validation findings: {err_reasons}"
            )

        # Prepend transparent degraded notice if any agent failed
        if failed_agents and not gate_blocked and not gate_requested_info and is_valid_val:
            completed_str = ", ".join(a.capitalize() for a in completed_agents)
            failed_str = ", ".join(a.capitalize() for a in failed_agents)
            transparency_header = (
                f"STATUS: PARTIAL (DEGRADED)\n"
                f"Completed: {completed_str}\n"
                f"Failed: {failed_str}\n"
                f"Degraded: Analysis for failed components ({failed_str}) could not be completed and related conclusions should be treated as provisional.\n\n"
            )
            if "STATUS: PARTIAL" not in final_deliverable and "STATUS: DEGRADED" not in final_deliverable:
                final_deliverable = f"{transparency_header}{final_deliverable}"

        # Determine overall request status semantics
        if not is_valid_val:
            overall_request_status = "failed"
        elif gate_blocked:
            overall_request_status = "blocked"
        elif gate_requested_info:
            overall_request_status = "requires_information"
        elif not selected_agents:
            overall_request_status = "completed"
        else:
            total_count = len(execution_statuses)
            success_count = len(completed_agents)
            failure_count = len(failed_agents)

            if failure_count > 0:
                overall_request_status = "partial" if success_count > 0 else "failed"
            elif success_count == total_count and total_count > 0:
                overall_request_status = "completed"
            elif failure_count == total_count:
                overall_request_status = "failed"
            else:
                overall_request_status = "partial" if success_count > 0 else "failed"

        # Determine agent_outputs representation
        if request.selected_agents is None:
            # For the general canonical workflow, output the canonical specialist agents
            final_agent_outputs = {k: v for k, v in agent_outputs.items() if k in CANONICAL_AGENTS}
        else:
            # When specific agents are requested, preserve all executed outputs
            final_agent_outputs = agent_outputs

        log_debug_agent_output("final answer", final_deliverable)
        return FinalResponse(
            request_id=getattr(request, "request_id", None) or state.get("request_id"),
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
            final_answer=final_deliverable,
            synthesis_result=agent_outputs.get("synthesizer"),
            validation_result=agent_outputs.get("output_validator"),
            execution_trace=execution_trace,
            errors=[s.error for s in execution_statuses if s.error],
            limitations=limitations,
            metadata={
                "selected_agents_count": len(selected_agents),
                "acquired_information_count": len(acquired_info),
            },
        )


# Backward-compatible alias
Coordinator = CHAICoordinator

__all__ = ["CHAICoordinator", "Coordinator", "CANONICAL_AGENTS"]
