from typing import Literal, Optional, List, Union
from pydantic import BaseModel, Field, field_validator
from backend.agents.researcher.models import ResearchResult


class StrategyInput(BaseModel):
    """
    Input contract for the Strategist Agent.
    Strictly consumes structured ResearchResult from the Researcher Agent.
    """
    problem: str = Field(description="The problem statement to develop a strategy for")
    research: ResearchResult = Field(description="Structured research findings from the Researcher Agent")
    context: Optional[Union[str, dict]] = Field(default=None, description="Optional domain or contextual background")

    @field_validator("problem")
    @classmethod
    def validate_problem_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Problem statement cannot be empty.")
        return v.strip()


class StrategyResult(BaseModel):
    """
    Output contract for the Strategist Agent.
    Encapsulates strategic direction, priorities, roadmap, trade-offs, and metrics.
    """
    agent: Literal["strategist"] = "strategist"
    status: Literal["completed", "failed"] = "completed"
    strategy: str = Field(default="", description="High-level practical strategic thesis and direction")
    priorities: list[str] = Field(
        default_factory=list,
        description="Ranked priorities grounded in user needs and constraints identified by research"
    )
    roadmap: list[str] = Field(
        default_factory=list,
        description="Logical execution phases and sequencing of steps"
    )
    tradeoffs: list[str] = Field(
        default_factory=list,
        description="Explicit trade-offs made given the constraints"
    )
    success_metrics: list[str] = Field(
        default_factory=list,
        description="Concrete, measurable metrics to validate success"
    )


# Backward compatibility alias
StrategistOutput = StrategyResult
