from typing import Optional, List, Dict, Any
from backend.core.schemas import SolveRequest, FinalResponse, AgentExecutionStatus
from backend.core.router import route_agents_for_problem
from backend.core.language import (
    detect_language,
    normalize_text,
    canonicalize_language,
    DEFAULT_LANGUAGE,
)
from backend.synthesis.synthesizer import Synthesizer
from backend.agents.researcher.agent import ResearcherAgent
from backend.agents.strategist.agent import StrategistAgent
from backend.agents.engineer.agent import EngineerAgent
from backend.agents.engineer.schemas import AgentStatus as EngStatus
from backend.agents.guardian.agent import GuardianAgent
from backend.agents.guardian.schemas import AgentStatus as GuardianStatus
from backend.agents.evaluator.agent import EvaluatorAgent
from backend.agents.evaluator.schemas import AgentStatus as EvalStatus
from backend.agents.security.agent import SecurityAgent
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class Coordinator:
    """
    Central orchestrator for the CHAI Multi-Agent System.

    Coordinates data flow across the 6 canonical specialized agents:
      1. Researcher (Problem analysis, user needs, constraints, assumptions)
      2. Strategist (Priorities, roadmap, trade-offs grounded in research)
      3. Engineer (Technical architecture, components, data flow, APIs)
      4. Guardian (Safety, ethics, privacy, misuse, human oversight)
      5. Security (Technical cybersecurity, attack surfaces, threat mitigations)
      6. Evaluator (Cross-agent consistency, conflicts, requirement coverage)
    """

    def __init__(
        self,
        researcher: Optional[ResearcherAgent] = None,
        strategist: Optional[StrategistAgent] = None,
        engineer: Optional[EngineerAgent] = None,
        guardian: Optional[GuardianAgent] = None,
        evaluator: Optional[EvaluatorAgent] = None,
        security: Optional[SecurityAgent] = None,
        synthesizer: Optional[Synthesizer] = None,
    ):
        self.researcher = researcher or ResearcherAgent()
        self.strategist = strategist or StrategistAgent()
        self.engineer = engineer or EngineerAgent()
        self.guardian = guardian or GuardianAgent()
        self.evaluator = evaluator or EvaluatorAgent()
        self.security = security or SecurityAgent()
        self.synthesizer = synthesizer or Synthesizer()

    async def process_request(self, request: SolveRequest) -> FinalResponse:
        logger.info(f"Processing request: {request.problem}")

        original_problem = request.problem or ""
        normalized_problem = normalize_text(original_problem)

        if not normalized_problem:
            return FinalResponse(
                request_status="failed",
                selected_agents=[],
                agent_outputs={},
                retrieved_sources=[],
                agent_execution_statuses=[],
                evaluation_findings=None,
                security_findings=None,
                detected_conflicts=[],
                final_synthesized_answer="Problem statement cannot be empty or whitespace only.",
                limitations=["Empty query"],
                language=DEFAULT_LANGUAGE,
            )

        # Resolve language: explicit user selection or automatic detection
        if request.language:
            resolved_lang = canonicalize_language(request.language) or DEFAULT_LANGUAGE
        else:
            detection = detect_language(normalized_problem)
            resolved_lang = detection.language

        logger.info(f"Resolved language '{resolved_lang}' for problem: {normalized_problem[:60]}...")

        # Determine which agents will run
        selected_agents = route_agents_for_problem(
            problem=normalized_problem,
            requested_agents=request.selected_agents,
        )

        agent_outputs: Dict[str, Any] = {}
        execution_statuses: List[AgentExecutionStatus] = []
        security_findings: Optional[Any] = None
        evaluation_findings: Optional[Any] = None
        detected_conflicts: List[str] = []

        lang_context_str = f"User language: {resolved_lang}"


        # -------------------------------------------------------------
        # 1. Researcher Agent
        # -------------------------------------------------------------
        if "researcher" in selected_agents:
            try:
                res_output = await self.researcher.run(
                    problem=normalized_problem,
                    context=lang_context_str,
                )
                agent_outputs["researcher"] = res_output.model_dump()
                res_status = "success" if res_output.status == "completed" else "failed"
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="researcher", status=res_status)
                )
            except Exception as e:
                logger.error(f"Researcher execution failed: {e}")
                agent_outputs["researcher"] = {
                    "agent": "researcher",
                    "status": "failed",
                    "key_findings": [],
                    "user_needs": [],
                    "constraints": [],
                    "assumptions": [],
                    "open_questions": [],
                    "sources": [],
                }
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="researcher", status="failed", error=str(e))
                )

        # -------------------------------------------------------------
        # 2. Strategist Agent (consumes Researcher output)
        # -------------------------------------------------------------
        if "strategist" in selected_agents:
            research_input = agent_outputs.get(
                "researcher",
                {
                    "agent": "researcher",
                    "status": "failed",
                    "key_findings": [],
                    "user_needs": [],
                    "constraints": [],
                    "assumptions": [],
                    "open_questions": [],
                    "sources": [],
                },
            )
            try:
                strat_output = await self.strategist.run(
                    problem=normalized_problem,
                    research=research_input,
                    context=lang_context_str,
                )
                agent_outputs["strategist"] = strat_output.model_dump()
                strat_status = "success" if strat_output.status == "completed" else "failed"
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="strategist", status=strat_status)
                )
            except Exception as e:
                logger.error(f"Strategist execution failed: {e}")
                agent_outputs["strategist"] = {
                    "agent": "strategist",
                    "status": "failed",
                    "strategy": "",
                    "priorities": [],
                    "roadmap": [],
                    "tradeoffs": [],
                    "success_metrics": [],
                }
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="strategist", status="failed", error=str(e))
                )

        # -------------------------------------------------------------
        # 3. Engineer Agent (consumes Researcher and Strategist context)
        # -------------------------------------------------------------
        if "engineer" in selected_agents:
            context_for_eng = {
                "researcher": agent_outputs.get("researcher"),
                "strategist": agent_outputs.get("strategist"),
                "language": resolved_lang,
                "user_language": resolved_lang,
            }
            try:
                eng_output = await self.engineer.run(
                    problem=normalized_problem,
                    context=context_for_eng,
                )
                agent_outputs["engineer"] = eng_output.model_dump()
                eng_status = "success"
                if (
                    eng_output.engineer_result
                    and getattr(eng_output.engineer_result, "status", None) == EngStatus.FAILED
                ):
                    eng_status = "failed"
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="engineer", status=eng_status)
                )
            except Exception as e:
                logger.error(f"Engineer execution failed: {e}")
                agent_outputs["engineer"] = {
                    "technical_architecture": "",
                    "recommended_technologies": [],
                    "components_and_apis": [],
                    "data_flow": "",
                    "implementation_plan": [],
                }
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="engineer", status="failed", error=str(e))
                )

        # -------------------------------------------------------------
        # 4. Guardian Agent (consumes upstream outputs for safety review)
        # -------------------------------------------------------------
        if "guardian" in selected_agents:
            context_for_guardian = {
                "researcher": agent_outputs.get("researcher"),
                "strategist": agent_outputs.get("strategist"),
                "engineer": agent_outputs.get("engineer"),
                "language": resolved_lang,
                "user_language": resolved_lang,
            }
            try:
                guardian_output = await self.guardian.run(
                    problem=normalized_problem,
                    context=context_for_guardian,
                )
                agent_outputs["guardian"] = guardian_output.model_dump()
                guardian_status = "success"
                if (
                    guardian_output.guardian_result
                    and getattr(guardian_output.guardian_result, "status", None) == GuardianStatus.FAILED
                ):
                    guardian_status = "failed"
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="guardian", status=guardian_status)
                )
            except Exception as e:
                logger.error(f"Guardian execution failed: {e}")
                agent_outputs["guardian"] = {
                    "safety_and_privacy_risks": [],
                    "reliability_and_ethical_risks": [],
                    "unsafe_assumptions": [],
                    "limitations": [],
                    "recommended_mitigations": [],
                }
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="guardian", status="failed", error=str(e))
                )

        # -------------------------------------------------------------
        # 5. Security Agent (technical cybersecurity review)
        # -------------------------------------------------------------
        if "security" in selected_agents:
            try:
                sec_output = await self.security.run(
                    problem=normalized_problem,
                    context=lang_context_str,
                    engineering=agent_outputs.get("engineer"),
                    research=agent_outputs.get("researcher"),
                    strategy=agent_outputs.get("strategist"),
                )
                security_findings = sec_output.model_dump()
                agent_outputs["security"] = security_findings
                sec_status = "success" if sec_output.status == "completed" else "failed"
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="security", status=sec_status)
                )
            except Exception as e:
                logger.error(f"Security execution failed: {e}")
                security_findings = None
                agent_outputs["security"] = {
                    "agent": "security",
                    "status": "failed",
                    "security_summary": "",
                    "threats": [],
                    "mitigations": [],
                }
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="security", status="failed", error=str(e))
                )

        # -------------------------------------------------------------
        # 6. Evaluator Agent (cross-agent consistency and conflict review)
        # -------------------------------------------------------------
        if "evaluator" in selected_agents:
            context_for_eval = {
                "all_outputs": agent_outputs,
                "language": resolved_lang,
                "user_language": resolved_lang,
            }
            try:
                eval_output = await self.evaluator.run(
                    problem=normalized_problem,
                    context=context_for_eval,
                )
                evaluation_findings = eval_output.model_dump()
                agent_outputs["evaluator"] = evaluation_findings
                detected_conflicts = list(eval_output.detected_contradictions)
                eval_status = "success"
                if (
                    eval_output.evaluator_result
                    and getattr(eval_output.evaluator_result, "status", None) == EvalStatus.FAILED
                ):
                    eval_status = "failed"
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="evaluator", status=eval_status)
                )
            except Exception as e:
                logger.error(f"Evaluator execution failed: {e}")
                evaluation_findings = None
                detected_conflicts = []
                agent_outputs["evaluator"] = {
                    "detected_contradictions": [],
                    "evaluator_result": None,
                }
                execution_statuses.append(
                    AgentExecutionStatus(agent_name="evaluator", status="failed", error=str(e))
                )

        # -------------------------------------------------------------
        # Synthesis & Final Response Formatting
        # -------------------------------------------------------------
        # Determine overall request status
        has_critical_failure = all(s.status == "failed" for s in execution_statuses)
        request_status = "failed" if (execution_statuses and has_critical_failure) else "completed"

        # Extract source references provenance
        res_dict = agent_outputs.get("researcher", {})
        retrieved_sources: List[str] = []
        if isinstance(res_dict.get("sources"), list):
            for s in res_dict["sources"]:
                if isinstance(s, dict) and s.get("title"):
                    retrieved_sources.append(s["title"])
                elif isinstance(s, str):
                    retrieved_sources.append(s)
        elif isinstance(res_dict.get("source_references"), list):
            retrieved_sources = [str(s) for s in res_dict["source_references"]]

        # Extract limitations
        limitations = agent_outputs.get("guardian", {}).get("limitations", [])

        # Produce final synthesized answer in the user's requested language
        final_answer = await self.synthesizer.synthesize(
            problem=normalized_problem,
            agent_outputs=agent_outputs,
            detected_conflicts=detected_conflicts,
            language=resolved_lang,
            limitations=limitations,
        )

        # Provide both canonical lowercase and TitleCase keys for frontend compatibility
        formatted_agent_outputs = dict(agent_outputs)
        for k, v in list(agent_outputs.items()):
            if isinstance(k, str):
                formatted_agent_outputs[k.capitalize()] = v

        return FinalResponse(
            request_status=request_status,
            selected_agents=selected_agents,
            agent_outputs=formatted_agent_outputs,
            retrieved_sources=retrieved_sources,
            agent_execution_statuses=execution_statuses,
            evaluation_findings=evaluation_findings,
            security_findings=security_findings,
            detected_conflicts=detected_conflicts,
            final_synthesized_answer=final_answer,
            limitations=limitations,
            language=resolved_lang,
        )

