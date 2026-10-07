"""
Coordinator module for CHAI (Coordinated Hybrid Agentic Intelligence).
Orchestrates multi-agent execution via a compiled LangGraph StateGraph,
managing state, error isolation, trace capture, and final response synthesis.
"""
from typing import Optional, Any, Dict, List
from backend.core.schemas import (
    SolveRequest,
    FinalResponse,
    AgentExecutionStatus,
    CHAIExecutionResult,
)
from backend.core.state import create_initial_state, CHAIState, get_canonical_agent_result
from backend.core.workflow import build_chai_workflow
from backend.information.service import InformationAcquisitionService
from backend.agents.researcher.agent import ResearcherAgent
from backend.agents.strategist.agent import StrategistAgent
from backend.agents.engineer.agent import EngineerAgent
from backend.agents.guardian.agent import GuardianAgent
from backend.agents.security.agent import SecurityAgent
from backend.agents.evaluator.agent import EvaluatorAgent
from backend.synthesis.synthesizer import Synthesizer
from backend.validation.output_validator import OutputValidator
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class CHAICoordinator:
    """
    CHAI Coordinator: manages the lifecycle and execution of requests through
    the LangGraph multi-agent StateGraph.

    Ensures:
    - Agents do not directly invoke one another.
    - Context passes through strongly typed shared state.
    - Upstream agent findings are treated as reference data, not instructions.
    - Errors in individual agents are isolated without crashing the pipeline.
    """

    def __init__(
        self,
        researcher: Optional[Any] = None,
        strategist: Optional[Any] = None,
        engineer: Optional[Any] = None,
        guardian: Optional[Any] = None,
        security: Optional[Any] = None,
        evaluator: Optional[Any] = None,
        information_acquisition: Optional[Any] = None,
        synthesizer: Optional[Any] = None,
        output_validator: Optional[Any] = None,
        **kwargs: Any,
    ):
        self.information_acquisition = information_acquisition or InformationAcquisitionService()
        self.researcher = researcher or ResearcherAgent()
        self.strategist = strategist or StrategistAgent()
        self.engineer = engineer or EngineerAgent()
        self.guardian = guardian or GuardianAgent()
        self.security = security or SecurityAgent()
        self.evaluator = evaluator or EvaluatorAgent()
        self.synthesizer = synthesizer or Synthesizer()
        self.output_validator = output_validator or OutputValidator()

        self._agent_instances = {
            "information_acquisition": self.information_acquisition,
            "researcher": self.researcher,
            "strategist": self.strategist,
            "engineer": self.engineer,
            "guardian": self.guardian,
            "security": self.security,
            "evaluator": self.evaluator,
            "synthesizer": self.synthesizer,
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
        """
        Executes a user request through the compiled LangGraph StateGraph.

        1. Initializes request-scoped CHAIState.
        2. Invokes the StateGraph asynchronously.
        3. Formulates a backward-compatible and schema-compliant FinalResponse.
        """
        logger.info(f"Coordinator: initiating workflow for problem: '{request.problem}'")

        initial_state = create_initial_state(
            problem=request.problem,
            user_id=getattr(request, "user_id", None),
            context=getattr(request, "context", None),
        )

        try:
            final_state: CHAIState = await self.graph.ainvoke(initial_state)
        except Exception as e:
            logger.critical(f"Coordinator: unhandled graph execution error: {e}", exc_info=True)
            return FinalResponse(
                request_status="failed",
                selected_agents=[],
                agent_outputs={},
                retrieved_sources=[],
                agent_execution_statuses=[],
                final_synthesized_answer=f"Execution error: {type(e).__name__}",
                final_answer=None,
                errors=[str(e)],
            )

        # -----------------------------------------------------------------
        # Build Response from State
        # -----------------------------------------------------------------
        route = final_state.get("route", "complex")
        complexity = final_state.get("complexity", "high")
        agent_outputs: Dict[str, Any] = final_state.get("agent_outputs", {})
        execution_trace: List[Dict[str, Any]] = final_state.get("execution_trace", [])
        completed_agents = set(final_state.get("completed_agents", []))
        failed_agents = set(final_state.get("failed_agents", []))
        all_agent_names = ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"]

        # Map execution statuses
        agent_execution_statuses: List[AgentExecutionStatus] = []
        if route == "simple":
            selected_agents = []
            agent_outputs = {}
            final_answer_text = final_state.get("final_answer") or f"Direct Answer:\n{request.problem}"
            res_status = "failed" if final_state.get("execution_status") == "failed" else "completed"
        elif "researcher" in failed_agents or final_state.get("execution_status") == "failed":
            # Hard stop on Researcher failure: do not execute downstream agents or fabricate final answer
            selected_agents = ["researcher"]
            agent_outputs = {}
            res_status = "failed"
            trace_err = next((t.get("error") for t in execution_trace if t.get("agent") == "researcher"), None)
            res_err = trace_err or "Researcher agent failed. Unable to continue the requested analysis."
            agent_execution_statuses.append(
                AgentExecutionStatus(
                    agent_name="researcher",
                    status="failed",
                    error=res_err,
                )
            )
            final_answer_text = "Researcher agent failed. Unable to continue the requested analysis."
        else:
            res_status = "completed"
            selected_agents = all_agent_names
            for name in all_agent_names:
                if name in completed_agents:
                    status = "success"
                    err = None
                elif name in failed_agents:
                    status = "failed"
                    trace_err = next((t.get("error") for t in execution_trace if t.get("agent") == name), None)
                    err = trace_err or f"{name.capitalize()} failed"
                else:
                    status = "failed"
                    err = "Agent was not executed"

                trace_item = next((t for t in execution_trace if t.get("agent") == name), None)
                duration = trace_item.get("duration_ms") if trace_item else None
                ts = trace_item.get("timestamp") if trace_item else None
                agent_execution_statuses.append(
                    AgentExecutionStatus(
                        agent_name=name,
                        status=status,
                        error=err,
                        duration_ms=duration,
                        timestamp=ts,
                    )
                )

            parts = ["Based on the comprehensive analysis of our specialized agents:"]
            if "strategist" in agent_outputs:
                st = agent_outputs["strategist"]
                desc = st.get("strategy") or st.get("strategy_overview")
                if desc:
                    parts.append(f"\nStrategic Thesis:\n{desc}")

            if "engineer" in agent_outputs:
                eng = agent_outputs["engineer"]
                arch = eng.get("technical_architecture") or (eng.get("engineer_result") or {}).get("problem_understanding")
                if arch:
                    parts.append(f"\nArchitecture & Technical Design:\n{arch}")

            if "security" in agent_outputs and agent_outputs["security"].get("security_summary"):
                parts.append(f"\nCybersecurity & Protection:\n{agent_outputs['security']['security_summary']}")

            if "guardian" in agent_outputs:
                g = agent_outputs["guardian"]
                safeguards = g.get("recommended_mitigations") or (g.get("guardian_result") or {}).get("safety_assessment")
                if safeguards:
                    parts.append(f"\nSafety & Ethical Safeguards:\n{safeguards}")

            if "evaluator" in agent_outputs:
                ev = agent_outputs["evaluator"]
                assessment = (ev.get("evaluator_result") or {}).get("overall_assessment") or ev.get("detected_contradictions")
                if assessment:
                    parts.append(f"\nCross-Agent Evaluation:\n{assessment}")

            synthesis_obj = get_canonical_agent_result(final_state, "synthesizer")
            if synthesis_obj and getattr(synthesis_obj, "final_text", None):
                final_answer_text = synthesis_obj.final_text
            elif isinstance(synthesis_obj, dict) and synthesis_obj.get("final_text"):
                final_answer_text = synthesis_obj["final_text"]
            elif final_state.get("final_answer"):
                final_answer_text = final_state["final_answer"]
            else:
                final_answer_text = "\n".join(parts)

        # Extract sources
        retrieved_sources: List[str] = list(final_state.get("sources", []))
        if not retrieved_sources and "researcher" in agent_outputs:
            raw_sources = agent_outputs["researcher"].get("sources", []) or agent_outputs["researcher"].get("source_references", [])
            for s in raw_sources:
                if isinstance(s, dict):
                    retrieved_sources.append(s.get("title") or s.get("url") or str(s))
                elif isinstance(s, str):
                    retrieved_sources.append(s)

        # Extract limitations
        limitations: List[str] = []
        if "guardian" in agent_outputs:
            limitations = agent_outputs["guardian"].get("limitations", []) or []

        # Retain specialized domain agents for response.agent_outputs
        specialist_outputs = {k: v for k, v in agent_outputs.items() if k in all_agent_names}

        return FinalResponse(
            request_id=final_state.get("request_id"),
            request_status=res_status,
            status=res_status,
            route=route,
            complexity=complexity,
            selected_agents=selected_agents,
            agent_outputs=specialist_outputs,
            retrieved_sources=retrieved_sources if "researcher" not in failed_agents and route != "simple" else [],
            acquired_information=final_state.get("acquired_information", []),
            agent_execution_statuses=agent_execution_statuses,
            evaluation_findings=agent_outputs.get("evaluator"),
            security_findings=agent_outputs.get("security"),
            detected_conflicts=final_state.get("conflicts", []),
            final_synthesized_answer=final_answer_text,
            final_answer=final_answer_text,
            synthesis_result=final_state.get("synthesis_result"),
            validation_result=final_state.get("validation_result"),
            execution_trace=execution_trace,
            errors=final_state.get("errors", []),
            limitations=limitations,
            metadata=final_state.get("metadata", {}),
        )


# Backward-compatible alias
Coordinator = CHAICoordinator

__all__ = ["CHAICoordinator", "Coordinator"]
