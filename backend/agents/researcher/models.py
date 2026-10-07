from typing import Literal, Optional, Any
from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    """
    Provenance representation for sources referenced or provided.
    Never fabricates fake URLs.
    """
    title: str = Field(description="Title or descriptive label of the source")
    url: Optional[str] = Field(default=None, description="Verified URL if available, otherwise None")
    source_type: str = Field(default="document", description="Source category, e.g., 'document', 'web', 'user_provided'")


class ResearchInput(BaseModel):
    """
    Flexible input model for the Researcher Agent.
    Validates that problem statement is non-empty.
    """
    problem: str = Field(description="User problem statement or requirements to investigate")
    context: Optional[str] = Field(default=None, description="Optional domain or contextual background")
    acquired_information: list[Any] = Field(default_factory=list, description="Pre-acquired evidence or records")
    sources: list[Source] = Field(default_factory=list, description="Explicit sources provided to the agent")

    @field_validator("problem")
    @classmethod
    def validate_problem_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Problem statement cannot be empty.")
        return v.strip()


class ResearchResult(BaseModel):
    """
    Strict output contract for the Researcher Agent.
    Encapsulates problem analysis without designing downstream solutions.
    """
    agent: Literal["researcher"] = "researcher"
    status: Literal["completed", "failed"] = "completed"
    key_findings: list[str] = Field(
        default_factory=list,
        description="Core observations and factual findings derived from the problem and provided information"
    )
    user_needs: list[str] = Field(
        default_factory=list,
        description="Explicit and implicit needs of users and stakeholders"
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Operational, technical, regulatory, or environmental constraints identified"
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Working assumptions made where verified data is not yet established"
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Unresolved questions and information gaps that must be answered before design"
    )
    sources: list[Source] = Field(
        default_factory=list,
        description="Verified provenance sources. Empty if no external sources were supplied or accessed."
    )


# Backward compatibility alias for any existing code
ResearcherOutput = ResearchResult
