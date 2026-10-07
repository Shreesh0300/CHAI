from backend.core.schemas import SolveRequest, FinalResponse, AgentExecutionStatus
from backend.agents.researcher.agent import ResearcherAgent
from backend.agents.strategist.agent import StrategistAgent
from backend.agents.engineer.agent import EngineerAgent
from backend.agents.guardian.agent import GuardianAgent
from backend.agents.evaluator.agent import EvaluatorAgent
from backend.agents.security.agent import SecurityAgent
from backend.shared.logger import get_logger

logger = get_logger(__name__)

class Coordinator:
    def __init__(self):
        self.researcher = ResearcherAgent()
        self.strategist = StrategistAgent()
        self.engineer = EngineerAgent()
        self.guardian = GuardianAgent()
        self.evaluator = EvaluatorAgent()
        self.security = SecurityAgent()
        
    async def process_request(self, request: SolveRequest) -> FinalResponse:
        logger.info(f"Processing request: {request.problem}")
        
        agent_outputs = {}
        execution_statuses = []
        
        # 1. Researcher
        try:
            res_output = await self.researcher.run(request.problem)
            agent_outputs["researcher"] = res_output.model_dump()
            execution_statuses.append(AgentExecutionStatus(agent_name="researcher", status="success"))
        except Exception as e:
            execution_statuses.append(AgentExecutionStatus(agent_name="researcher", status="failed", error=str(e)))
            
        # 2. Strategist
        context_for_strat = {"researcher_output": agent_outputs.get("researcher", {})}
        try:
            strat_output = await self.strategist.run(request.problem, context=context_for_strat)
            agent_outputs["strategist"] = strat_output.model_dump()
            execution_statuses.append(AgentExecutionStatus(agent_name="strategist", status="success"))
        except Exception as e:
            execution_statuses.append(AgentExecutionStatus(agent_name="strategist", status="failed", error=str(e)))
            
        # 3. Engineer
        context_for_eng = {"researcher": agent_outputs.get("researcher"), "strategist": agent_outputs.get("strategist")}
        try:
            eng_output = await self.engineer.run(request.problem, context=context_for_eng)
            agent_outputs["engineer"] = eng_output.model_dump()
            execution_statuses.append(AgentExecutionStatus(agent_name="engineer", status="success"))
        except Exception as e:
            execution_statuses.append(AgentExecutionStatus(agent_name="engineer", status="failed", error=str(e)))
            
        # 4. Guardian
        context_for_guardian = {"engineer": agent_outputs.get("engineer"), "strategist": agent_outputs.get("strategist")}
        try:
            guardian_output = await self.guardian.run(request.problem, context=context_for_guardian)
            agent_outputs["guardian"] = guardian_output.model_dump()
            execution_statuses.append(AgentExecutionStatus(agent_name="guardian", status="success"))
        except Exception as e:
            execution_statuses.append(AgentExecutionStatus(agent_name="guardian", status="failed", error=str(e)))
            
        # 5. Security
        context_for_sec = {"engineer": agent_outputs.get("engineer")}
        try:
            sec_output = await self.security.run(request.problem, context=context_for_sec)
            security_findings = sec_output.model_dump()
            execution_statuses.append(AgentExecutionStatus(agent_name="security", status="success"))
        except Exception as e:
            security_findings = None
            execution_statuses.append(AgentExecutionStatus(agent_name="security", status="failed", error=str(e)))
            
        # 6. Evaluator
        context_for_eval = {"all_outputs": agent_outputs}
        try:
            eval_output = await self.evaluator.run(request.problem, context=context_for_eval)
            evaluation_findings = eval_output.model_dump()
            execution_statuses.append(AgentExecutionStatus(agent_name="evaluator", status="success"))
            detected_conflicts = eval_output.detected_contradictions
        except Exception as e:
            evaluation_findings = None
            detected_conflicts = []
            execution_statuses.append(AgentExecutionStatus(agent_name="evaluator", status="failed", error=str(e)))

        # Final Synthesis
        final_answer = "Based on the comprehensive analysis of our specialized agents:\\n"
        if "strategist" in agent_outputs:
            final_answer += f"\\nStrategy:\\n{agent_outputs['strategist'].get('strategy_overview', '')}\\n"
        if "engineer" in agent_outputs:
            final_answer += f"\\nArchitecture:\\n{agent_outputs['engineer'].get('technical_architecture', '')}\\n"
            
        return FinalResponse(
            request_status="completed",
            selected_agents=["researcher", "strategist", "engineer", "guardian", "security", "evaluator"],
            agent_outputs=agent_outputs,
            retrieved_sources=agent_outputs.get("researcher", {}).get("source_references", []),
            agent_execution_statuses=execution_statuses,
            evaluation_findings=evaluation_findings,
            security_findings=security_findings,
            detected_conflicts=detected_conflicts,
            final_synthesized_answer=final_answer,
            limitations=agent_outputs.get("guardian", {}).get("limitations", [])
        )
