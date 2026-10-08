from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Any, Dict

class SolveRequest(BaseModel):
    problem: str = Field(..., min_length=1, description="The user's problem or query.")
    selected_agents: Optional[List[str]] = Field(
        default=None,
        description="Optional list of specific agents to execute. Defaults to all 6 agents."
    )
    language: Optional[str] = Field(
        default=None,
        description="Optional ISO language code ('en', 'hi', 'kn'). Auto-detected if omitted."
    )

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        from backend.core.language import canonicalize_language
        canon = canonicalize_language(v)
        if canon is None:
            raise ValueError(f"Unsupported language '{v}'. Supported languages are: 'en', 'hi', 'kn', 'sa'.")
        return canon

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
    language: str = Field(default="en", description="Resolved ISO language code ('en', 'hi', 'kn').")

