from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class SolveRequest(BaseModel):
    problem: str = Field(..., description="The user's problem or query.")
    selected_agents: Optional[List[str]] = Field(default=None, description="Optional override list of agents to execute.")

class AgentExecutionStatus(BaseModel):
    agent_name: str
    status: str
    error: Optional[str] = None

class FinalResponse(BaseModel):
    request_status: str
    selected_agents: List[str]
    agent_outputs: Dict[str, Any]
    retrieved_sources: List[str]
    agent_execution_statuses: List[AgentExecutionStatus]
    evaluation_findings: Optional[Any] = None
    security_findings: Optional[Any] = None
    detected_conflicts: List[str] = []
    final_synthesized_answer: str
    limitations: Optional[List[str]] = None
