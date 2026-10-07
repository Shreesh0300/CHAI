from typing import List, Optional, Any, Dict
from backend.core.schemas import SolveRequest, FinalResponse, AgentExecutionStatus
from backend.agents.researcher.agent import ResearcherAgent
from backend.agents.strategist.agent import StrategistAgent
from backend.agents.engineer.agent import EngineerAgent
from backend.agents.guardian.agent import GuardianAgent
from backend.agents.evaluator.agent import EvaluatorAgent
from backend.agents.security.agent import SecurityAgent
from backend.agents.conflict_resolver.agent import ConflictResolverAgent
from backend.agents.synthesizer.agent import SynthesizerAgent
from backend.agents.reliability_monitor.agent import ReliabilityMonitorAgent
from backend.agents.reliability_monitor.schemas import ReliabilityAction
from backend.validation.output_validator import OutputValidator
from backend.shared.logger import get_logger

logger = get_logger(__name__)

CANONICAL_AGENTS = ["researcher", "strategist", "engineer", "guardian", "security", "evaluator"]


def is_simple_query(problem: str) -> bool:
    """Detect simple informational queries that do not require full multi-agent analysis."""
    p = problem.strip().lower()
    simple_patterns = [
        "what is a python list",
        "what is python list",
        "explain python list",
        "what is a list in python",
    ]
    return any(pattern in p for pattern in simple_patterns)


class Coordinator:
    def __init__(
        self,
        researcher=None,
        strategist=None,
        engineer=None,
        guardian=None,
        security=None,
        evaluator=None,
        conflict_resolver=None,
        synthesizer=None,
        reliability_monitor=None,
        output_validator=None,
    ):
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
        
    async def process_request(self, request: SolveRequest) -> FinalResponse:
        logger.info(f"Processing request: {request.problem}")
        
        agent_outputs: Dict[str, Any] = {}
        execution_statuses: List[AgentExecutionStatus] = []

        # Determine which agents to execute
        if request.selected_agents is not None:
            selected_agents = [a.lower().strip() for a in request.selected_agents]
        elif is_simple_query(request.problem):
            # No specialized agents selected for direct/simple response
            selected_agents = []
        else:
            selected_agents = list(CANONICAL_AGENTS)
        
        # 1. Researcher
        if "researcher" in selected_agents:
            try:
                res_output = await self.researcher.run(request.problem)
                res_dump = res_output.model_dump() if hasattr(res_output, "model_dump") else dict(res_output)
                agent_outputs["researcher"] = res_dump
                status_val = getattr(res_output, "status", None) or res_dump.get("status")
                if str(status_val).lower() in ("completed", "success"):
                    execution_statuses.append(AgentExecutionStatus(agent_name="researcher", status="success"))
                else:
                    execution_statuses.append(AgentExecutionStatus(agent_name="researcher", status="failed", error="Researcher returned failed status"))
            except Exception as e:
                logger.error(f"Researcher execution error: {e}")
                execution_statuses.append(AgentExecutionStatus(agent_name="researcher", status="failed", error=str(e)))
            
        # 2. Strategist
        if "strategist" in selected_agents:
            research_data = agent_outputs.get("researcher")
            context_for_strat = {"researcher_output": research_data or {}}
            try:
                strat_output = await self.strategist.run(
                    problem=request.problem,
                    research=research_data or {},
                    context=context_for_strat,
                )
                strat_dump = strat_output.model_dump() if hasattr(strat_output, "model_dump") else dict(strat_output)
                agent_outputs["strategist"] = strat_dump
                status_val = getattr(strat_output, "status", None) or strat_dump.get("status")
                if str(status_val).lower() in ("completed", "success"):
                    execution_statuses.append(AgentExecutionStatus(agent_name="strategist", status="success"))
                else:
                    execution_statuses.append(AgentExecutionStatus(agent_name="strategist", status="failed", error="Strategist returned failed status"))
            except Exception as e:
                logger.error(f"Strategist execution error: {e}")
                execution_statuses.append(AgentExecutionStatus(agent_name="strategist", status="failed", error=str(e)))
            
        # 3. Engineer
        if "engineer" in selected_agents:
            context_for_eng = {
                "researcher": agent_outputs.get("researcher"),
                "strategist": agent_outputs.get("strategist"),
            }
            try:
                eng_output = await self.engineer.run(request.problem, context=context_for_eng)
                eng_dump = eng_output.model_dump() if hasattr(eng_output, "model_dump") else dict(eng_output)
                agent_outputs["engineer"] = eng_dump
                status_val = getattr(eng_output, "status", None) or eng_dump.get("status")
                if str(status_val).lower() in ("completed", "success"):
                    execution_statuses.append(AgentExecutionStatus(agent_name="engineer", status="success"))
                else:
                    execution_statuses.append(AgentExecutionStatus(agent_name="engineer", status="failed", error="Engineer returned failed status"))
            except Exception as e:
                logger.error(f"Engineer execution error: {e}")
                execution_statuses.append(AgentExecutionStatus(agent_name="engineer", status="failed", error=str(e)))
            
        # 4. Guardian
        if "guardian" in selected_agents:
            context_for_guardian = {
                "engineer": agent_outputs.get("engineer"),
                "strategist": agent_outputs.get("strategist"),
                "researcher": agent_outputs.get("researcher"),
            }
            try:
                guardian_output = await self.guardian.run(request.problem, context=context_for_guardian)
                guard_dump = guardian_output.model_dump() if hasattr(guardian_output, "model_dump") else dict(guardian_output)
                agent_outputs["guardian"] = guard_dump
                status_val = getattr(guardian_output, "status", None) or guard_dump.get("status")
                if str(status_val).lower() in ("completed", "success"):
                    execution_statuses.append(AgentExecutionStatus(agent_name="guardian", status="success"))
                else:
                    execution_statuses.append(AgentExecutionStatus(agent_name="guardian", status="failed", error="Guardian returned failed status"))
            except Exception as e:
                logger.error(f"Guardian execution error: {e}")
                execution_statuses.append(AgentExecutionStatus(agent_name="guardian", status="failed", error=str(e)))
            
        # 5. Security
        security_findings = None
        if "security" in selected_agents:
            context_for_sec = {
                "engineer": agent_outputs.get("engineer"),
                "researcher": agent_outputs.get("researcher"),
                "strategist": agent_outputs.get("strategist"),
            }
            try:
                sec_output = await self.security.run(
                    problem=request.problem,
                    engineering=agent_outputs.get("engineer"),
                    research=agent_outputs.get("researcher"),
                    strategy=agent_outputs.get("strategist"),
                    context=context_for_sec,
                )
                sec_dump = sec_output.model_dump() if hasattr(sec_output, "model_dump") else dict(sec_output)
                agent_outputs["security"] = sec_dump
                security_findings = sec_dump
                status_val = getattr(sec_output, "status", None) or sec_dump.get("status")
                if str(status_val).lower() in ("completed", "success"):
                    execution_statuses.append(AgentExecutionStatus(agent_name="security", status="success"))
                else:
                    execution_statuses.append(AgentExecutionStatus(agent_name="security", status="failed", error="Security returned failed status"))
            except Exception as e:
                logger.error(f"Security execution error: {e}")
                execution_statuses.append(AgentExecutionStatus(agent_name="security", status="failed", error=str(e)))
            
        # 6. Evaluator
        evaluation_findings = None
        detected_conflicts: List[str] = []
        if "evaluator" in selected_agents:
            context_for_eval = {"all_outputs": agent_outputs}
            try:
                eval_output = await self.evaluator.run(request.problem, context=context_for_eval)
                eval_dump = eval_output.model_dump() if hasattr(eval_output, "model_dump") else dict(eval_output)
                agent_outputs["evaluator"] = eval_dump
                evaluation_findings = eval_dump
                status_val = (
                    getattr(eval_output, "status", None)
                    or eval_dump.get("status")
                    or (eval_dump.get("evaluator_result") or {}).get("status")
                )
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    execution_statuses.append(AgentExecutionStatus(agent_name="evaluator", status="success"))
                else:
                    execution_statuses.append(AgentExecutionStatus(agent_name="evaluator", status="failed", error="Evaluator returned failed status"))
                detected_conflicts = getattr(eval_output, "detected_contradictions", []) or eval_dump.get("detected_contradictions", [])
            except Exception as e:
                logger.error(f"Evaluator execution error: {e}")
                execution_statuses.append(AgentExecutionStatus(agent_name="evaluator", status="failed", error=str(e)))

        # 7. Conflict Resolver
        if "conflict_resolver" in selected_agents:
            context_for_cr = {"all_outputs": agent_outputs}
            try:
                cr_output = await self.conflict_resolver.run(request.problem, context=context_for_cr)
                cr_dump = cr_output.model_dump() if hasattr(cr_output, "model_dump") else dict(cr_output)
                agent_outputs["conflict_resolver"] = cr_dump
                status_val = getattr(cr_output, "status", None) or cr_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    execution_statuses.append(AgentExecutionStatus(agent_name="conflict_resolver", status="success"))
                else:
                    execution_statuses.append(AgentExecutionStatus(agent_name="conflict_resolver", status="failed", error="Conflict Resolver returned failed status"))
            except Exception as e:
                logger.error(f"Conflict Resolver execution error: {e}")
                execution_statuses.append(AgentExecutionStatus(agent_name="conflict_resolver", status="failed", error=str(e)))

        # 8. Synthesizer
        if "synthesizer" in selected_agents:
            context_for_synth = {
                "all_outputs": agent_outputs,
                "execution_statuses": execution_statuses,
            }
            try:
                synth_output = await self.synthesizer.run(request.problem, context=context_for_synth)
                synth_dump = synth_output.model_dump() if hasattr(synth_output, "model_dump") else dict(synth_output)
                agent_outputs["synthesizer"] = synth_dump
                status_val = getattr(synth_output, "status", None) or synth_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    execution_statuses.append(AgentExecutionStatus(agent_name="synthesizer", status="success"))
                else:
                    execution_statuses.append(AgentExecutionStatus(agent_name="synthesizer", status="failed", error="Synthesizer returned failed status"))
                final_answer = synth_dump.get("final_answer", "") or ""
            except Exception as e:
                logger.error(f"Synthesizer execution error: {e}")
                execution_statuses.append(AgentExecutionStatus(agent_name="synthesizer", status="failed", error=str(e)))
                final_answer = ""
        else:
            if not selected_agents:
                final_answer = f"Direct response provided for: {request.problem}"
            else:
                final_answer = "Based on the comprehensive analysis of our specialized agents:\n"
            if "strategist" in agent_outputs:
                strat_txt = agent_outputs["strategist"].get("strategy") or agent_outputs["strategist"].get("strategy_overview", "")
                if strat_txt:
                    final_answer += f"\nStrategy:\n{strat_txt}\n"
            if "engineer" in agent_outputs:
                eng_txt = agent_outputs["engineer"].get("technical_architecture") or agent_outputs["engineer"].get("architecture_overview", "")
                if eng_txt:
                    final_answer += f"\nArchitecture:\n{eng_txt}\n"
            if "security" in agent_outputs:
                sec_txt = agent_outputs["security"].get("security_summary", "")
                if sec_txt:
                    final_answer += f"\nSecurity:\n{sec_txt}\n"
            if "evaluator" in agent_outputs:
                eval_txt = agent_outputs["evaluator"].get("overall_assessment", "")
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

        # Ensure internal synthesis is available in agent_outputs for downstream audit and gate isolation
        if "synthesizer" not in agent_outputs and final_answer:
            agent_outputs["synthesizer"] = {
                "agent": "synthesizer",
                "status": "completed",
                "final_answer": final_answer,
            }

        # 9. Reliability Monitor
        rm_action: Optional[ReliabilityAction] = None
        rm_dump: Dict[str, Any] = {}

        if "reliability_monitor" in selected_agents:
            context_for_rm = {
                "all_outputs": agent_outputs,
                "final_answer": final_answer,
                "execution_statuses": execution_statuses,
            }
            try:
                rm_output = await self.reliability_monitor.run(request.problem, context=context_for_rm)
                rm_dump = rm_output.model_dump() if hasattr(rm_output, "model_dump") else dict(rm_output)
                agent_outputs["reliability_monitor"] = rm_dump
                status_val = getattr(rm_output, "status", None) or rm_dump.get("status")
                val_str = status_val.value if hasattr(status_val, "value") else str(status_val or "")
                if val_str.lower() in ("completed", "success") or "completed" in val_str.lower():
                    execution_statuses.append(AgentExecutionStatus(agent_name="reliability_monitor", status="success"))
                else:
                    execution_statuses.append(AgentExecutionStatus(agent_name="reliability_monitor", status="failed", error="Reliability Monitor returned failed status"))

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
                execution_statuses.append(AgentExecutionStatus(agent_name="reliability_monitor", status="failed", error=str(e)))
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
        elif rm_action == ReliabilityAction.PROCEED_WITH_LIMITATIONS:
            delivered_answer = final_answer
        elif rm_action == ReliabilityAction.PROCEED:
            delivered_answer = final_answer

        # Sources from researcher
        sources: List[str] = []
        res_raw_sources = agent_outputs.get("researcher", {}).get("sources", []) or agent_outputs.get("researcher", {}).get("source_references", [])
        for s in res_raw_sources:
            if isinstance(s, dict):
                sources.append(s.get("title") or s.get("url") or str(s))
            elif isinstance(s, str):
                sources.append(s)
            elif hasattr(s, "title"):
                sources.append(s.title)

        # Limitations from guardian
        limitations = (
            agent_outputs.get("guardian", {}).get("limitations")
            or agent_outputs.get("guardian", {}).get("safety_risks")
            or []
        )

        # Preserve and attach Reliability Monitor limitations/concerns to final response layer
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
        try:
            validation_result = self.output_validator.validate(
                delivered_answer,
                context={"all_outputs": agent_outputs, "selected_agents": selected_agents},
            )
        except Exception as val_err:
            logger.error(f"Output Validator execution error: {val_err}")
            validation_result = OutputValidationResult(
                is_valid=False,
                errors=[f"Output Validator execution failure: {val_err}"],
                sanitized_output=None,
            )

        agent_outputs["output_validator"] = validation_result.model_dump()

        if validation_result.is_valid:
            final_deliverable = validation_result.sanitized_output or delivered_answer
        else:
            logger.warning(f"Output validation failed: {validation_result.errors}")
            err_reasons = "; ".join(validation_result.errors) if validation_result.errors else "Structural or operational validation failure"
            final_deliverable = (
                f"[DELIVERY BLOCKED] The generated response failed final delivery validation and cannot be delivered. "
                f"Validation findings: {err_reasons}"
            )

        # Determine overall request status semantics
        if not validation_result.is_valid:
            overall_request_status = "failed"
        elif gate_blocked:
            overall_request_status = "blocked"
        elif gate_requested_info:
            overall_request_status = "requires_information"
        elif not selected_agents:
            # Rule 4: If no agents are selected for a valid direct/simple response, preserve completed
            overall_request_status = "completed"
        else:
            total_count = len(selected_agents)
            success_count = sum(1 for s in execution_statuses if s.status.lower() in ("success", "completed"))
            failure_count = sum(1 for s in execution_statuses if s.status.lower() in ("failed", "failure", "error"))

            if success_count == total_count:
                # Rule 1: All selected agents complete successfully
                overall_request_status = "completed"
            elif success_count > 0 and failure_count > 0:
                # Rule 2: At least one selected agent succeeds and at least one fails
                overall_request_status = "partial"
            elif failure_count == total_count or success_count == 0:
                # Rule 3: All selected agents fail
                overall_request_status = "failed"
            else:
                overall_request_status = "partial" if success_count > 0 else "failed"

        return FinalResponse(
            request_status=overall_request_status,
            selected_agents=selected_agents,
            agent_outputs=agent_outputs,
            retrieved_sources=sources,
            agent_execution_statuses=execution_statuses,
            evaluation_findings=evaluation_findings,
            security_findings=security_findings,
            detected_conflicts=detected_conflicts,
            final_synthesized_answer=final_deliverable,
            limitations=limitations,
        )
