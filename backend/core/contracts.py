"""
Explicit typed contracts for the CHAI multi-agent workflow.

Defines the base AgentResult, input contracts for every agent in the pipeline,
and authoritative result models for Synthesis and Validation.
"""
from __future__ import annotations

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator

from backend.agents.researcher.models import ResearchResult, Source
from backend.agents.strategist.models import StrategyResult
from backend.agents.engineer.schemas import EngineerResult, EngineerOutput
from backend.agents.guardian.schemas import GuardianResult, GuardianOutput
from backend.agents.security.models import SecurityResult
from backend.agents.evaluator.schemas import EvaluatorResult, EvaluatorOutput


class AgentResult(BaseModel):
    """
    Common base contract for all agent execution results in CHAI.
    Specialized agent results (ResearchResult, StrategyResult, EngineerResult,
    GuardianResult, SecurityResult, EvaluatorResult) are authoritative.
    """
    agent: str = Field(..., description="Unique agent identifier")
    status: str = Field(default="completed", description="Execution status ('completed' or 'failed')")


# ---------------------------------------------------------------------------
# Typed Input Contracts for Workflow Agents
# ---------------------------------------------------------------------------

class ResearcherInputContract(BaseModel):
    """Explicit input contract consumed by the Researcher Agent."""
    problem: str = Field(..., description="User problem statement or requirements to investigate")
    context: Optional[str] = Field(default=None, description="Optional domain or contextual background")
    acquired_information: List[Any] = Field(default_factory=list, description="Pre-acquired evidence or web records")
    sources: List[Source] = Field(default_factory=list, description="Verified provenance source references")

    @field_validator("problem")
    @classmethod
    def validate_problem_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Problem statement cannot be empty.")
        return v.strip()


class StrategistInputContract(BaseModel):
    """Explicit input contract consumed by the Strategist Agent."""
    problem: str = Field(..., description="User problem statement")
    research: ResearchResult = Field(..., description="Authoritative ResearchResult from Researcher Agent")
    context: Optional[str] = Field(default=None, description="Optional domain or contextual background")

    @field_validator("problem")
    @classmethod
    def validate_problem_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Problem statement cannot be empty.")
        return v.strip()


class EngineerInputContract(BaseModel):
    """Explicit input contract consumed by the Engineer Agent."""
    problem: str = Field(..., description="User problem statement")
    research: Optional[ResearchResult] = Field(default=None, description="Authoritative research findings")
    strategy: Optional[StrategyResult] = Field(default=None, description="Authoritative strategic roadmap and priorities")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Context dictionary containing upstream findings")

    @field_validator("problem")
    @classmethod
    def validate_problem_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Problem statement cannot be empty.")
        return v.strip()


class GuardianInputContract(BaseModel):
    """Explicit input contract consumed by the Guardian Agent."""
    problem: str = Field(..., description="User problem statement")
    research: Optional[ResearchResult] = Field(default=None, description="Authoritative research findings")
    strategy: Optional[StrategyResult] = Field(default=None, description="Authoritative strategic roadmap and priorities")
    engineering: Optional[Union[EngineerResult, EngineerOutput, Dict[str, Any]]] = Field(
        default=None, description="Authoritative engineering specifications"
    )
    context: Optional[Dict[str, Any]] = Field(default=None, description="Context dictionary containing upstream findings")

    @field_validator("problem")
    @classmethod
    def validate_problem_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Problem statement cannot be empty.")
        return v.strip()


class SecurityInputContract(BaseModel):
    """Explicit input contract consumed by the Security Agent."""
    problem: str = Field(..., description="User problem statement")
    research: Optional[ResearchResult] = Field(default=None, description="Authoritative research findings")
    strategy: Optional[StrategyResult] = Field(default=None, description="Authoritative strategic roadmap and priorities")
    engineering: Optional[Union[EngineerResult, EngineerOutput, Dict[str, Any]]] = Field(
        default=None, description="Authoritative engineering specifications"
    )
    context: Optional[str] = Field(default=None, description="Optional domain or environmental details")

    @field_validator("problem")
    @classmethod
    def validate_problem_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Problem statement cannot be empty.")
        return v.strip()


class EvaluatorInputContract(BaseModel):
    """Explicit input contract consumed by the Evaluator Agent."""
    problem: str = Field(..., description="User problem statement")
    research: Optional[ResearchResult] = Field(default=None, description="Authoritative research findings")
    strategy: Optional[StrategyResult] = Field(default=None, description="Authoritative strategic roadmap and priorities")
    engineering: Optional[Union[EngineerResult, EngineerOutput, Dict[str, Any]]] = Field(
        default=None, description="Authoritative engineering specifications"
    )
    guardian: Optional[Union[GuardianResult, GuardianOutput, Dict[str, Any]]] = Field(
        default=None, description="Authoritative guardian safety assessment"
    )
    security: Optional[SecurityResult] = Field(default=None, description="Authoritative security assessment")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Combined reference outputs for cross-evaluation")

    @field_validator("problem")
    @classmethod
    def validate_problem_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Problem statement cannot be empty.")
        return v.strip()


class SynthesizerInputContract(BaseModel):
    """Explicit input contract consumed by the Synthesizer module."""
    problem: str = Field(..., description="Original user query/problem statement")
    research: Optional[ResearchResult] = Field(default=None, description="Authoritative research findings")
    strategy: Optional[StrategyResult] = Field(default=None, description="Authoritative strategic roadmap and priorities")
    engineering: Optional[Union[EngineerResult, EngineerOutput, Dict[str, Any]]] = Field(
        default=None, description="Authoritative engineering specifications"
    )
    guardian: Optional[Union[GuardianResult, GuardianOutput, Dict[str, Any]]] = Field(
        default=None, description="Authoritative safety and ethical guardrails"
    )
    security: Optional[SecurityResult] = Field(default=None, description="Authoritative security assessment")
    evaluator: Optional[Union[EvaluatorResult, EvaluatorOutput, Dict[str, Any]]] = Field(
        default=None, description="Authoritative cross-agent evaluation findings"
    )
    sources: List[str] = Field(default_factory=list, description="All retrieved provenance sources")
    conflicts: List[str] = Field(default_factory=list, description="Contradictions detected across agents")
    all_agent_results: Dict[str, Any] = Field(default_factory=dict, description="All available agent outputs")

    @field_validator("problem")
    @classmethod
    def validate_problem_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Problem statement cannot be empty.")
        return v.strip()


# ---------------------------------------------------------------------------
# Synthesis and Validation Result Models
# ---------------------------------------------------------------------------

class SynthesisResult(AgentResult):
    """Authoritative structured output contract from the Synthesizer."""
    agent: str = Field(default="synthesizer", description="Identifier for synthesizer")
    status: str = Field(default="completed", description="Execution status")
    summary: str = Field(default="", description="Executive problem and requirements summary")
    reconciled_solution: str = Field(default="", description="Reconciled technical and strategic solution")
    key_tradeoffs: List[str] = Field(default_factory=list, description="Resolved trade-offs across perspectives")
    safeguards_summary: List[str] = Field(default_factory=list, description="Synthesized safety, ethical, and security safeguards")
    remaining_open_questions: List[str] = Field(default_factory=list, description="Unresolved gaps or open questions")
    sources: List[str] = Field(default_factory=list, description="Deduplicated provenance sources")
    final_text: str = Field(default="", description="Complete synthesized response text")


# Backward compatibility alias
FinalResult = SynthesisResult


class ValidationResult(AgentResult):
    """Authoritative structured output contract from the Output Validator."""
    agent: str = Field(default="output_validator", description="Identifier for output validator")
    status: str = Field(default="completed", description="Execution status")
    is_valid: bool = Field(default=True, description="Whether output passed all validation checks")
    issues: List[str] = Field(default_factory=list, description="Identified validation issues or warnings")
    sanitized_text: str = Field(default="", description="Sanitized, verified final answer text")


# Aliases for convenience
ResearcherInput = ResearcherInputContract
StrategistInput = StrategistInputContract
EngineerInput = EngineerInputContract
GuardianInput = GuardianInputContract
SecurityInput = SecurityInputContract
EvaluatorInput = EvaluatorInputContract
SynthesizerInput = SynthesizerInputContract

__all__ = [
    "AgentResult",
    "ResearcherInputContract",
    "StrategistInputContract",
    "EngineerInputContract",
    "GuardianInputContract",
    "SecurityInputContract",
    "EvaluatorInputContract",
    "SynthesizerInputContract",
    "ResearcherInput",
    "StrategistInput",
    "EngineerInput",
    "GuardianInput",
    "SecurityInput",
    "EvaluatorInput",
    "SynthesizerInput",
    "SynthesisResult",
    "FinalResult",
    "ValidationResult",
]
