"""
Structured Pydantic schemas for the CHAI Synthesizer Agent.

The Synthesizer Agent is the final composition layer of CHAI that converts
validated multi-agent perspectives, evaluator findings, and conflict resolutions
into ONE unified, coherent, evidence-grounded final response for the user.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    """Controlled status values for agent execution."""
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class KeyDecision(BaseModel):
    """A key architectural, strategic, or operational decision in the synthesized response."""
    decision: str = Field(..., description="The decision made in the synthesized outcome.")
    rationale: str = Field(..., description="Reasoning grounded in user requirements and agent findings.")
    supported_by: List[str] = Field(default_factory=list, description="Participating agents supporting this decision.")


class SupportingFinding(BaseModel):
    """Important evidence or perspective that directly supports the final answer."""
    finding: str = Field(..., description="The specific factual finding or recommendation.")
    source_agent: Optional[str] = Field(None, description="The agent where this finding originated.")
    significance: Optional[str] = Field(None, description="Why this finding is critical to the final outcome.")


class ResolvedConflict(BaseModel):
    """A disagreement or trade-off that was resolved through conflict resolution guidance."""
    conflict: str = Field(..., description="Description of the conflicting perspectives.")
    resolution: str = Field(..., description="The resolution adopted in the final answer.")
    source: Optional[str] = Field("conflict_resolver", description="Source of the resolution guidance.")


class UnresolvedConflict(BaseModel):
    """A conflict that cannot be reconciled without additional information or user input."""
    conflict: str = Field(..., description="Description of the unresolved disagreement.")
    reason_unresolved: str = Field(..., description="Why the conflict could not be reconciled.")
    impact: Optional[str] = Field(None, description="Impact or trade-off the user must evaluate.")


class ProvenanceItem(BaseModel):
    """Internal traceability item linking a key statement to participating agents."""
    statement: str = Field(..., description="Key conclusion or statement in the final answer.")
    supported_by: List[str] = Field(default_factory=list, description="Agents providing evidence for this statement.")


class SynthesizerResult(BaseModel):
    """
    The canonical structured output of the CHAI Synthesizer Agent.

    Contains the unified final response, key decisions, supporting findings,
    conflict statuses, limitations, assumptions, and internal provenance.
    """
    agent: str = Field(default="synthesizer", description="Agent identifier.")
    status: AgentStatus = Field(default=AgentStatus.COMPLETED, description="Execution status.")

    final_answer: str = Field(..., description="The unified, coherent, user-facing final outcome.")

    key_decisions: List[KeyDecision] = Field(
        default_factory=list, description="Key decisions made in formulating the final answer."
    )
    supporting_findings: List[SupportingFinding] = Field(
        default_factory=list, description="Important evidence supporting the final answer."
    )
    resolved_conflicts: List[ResolvedConflict] = Field(
        default_factory=list, description="Conflicts that were resolved."
    )
    unresolved_conflicts: List[UnresolvedConflict] = Field(
        default_factory=list, description="Disagreements remaining unresolved."
    )
    limitations: List[str] = Field(
        default_factory=list, description="Important limitations and boundaries."
    )
    assumptions: List[str] = Field(
        default_factory=list, description="Assumptions made during synthesis."
    )
    missing_information: List[str] = Field(
        default_factory=list, description="Missing data required for full certainty."
    )
    provenance: List[ProvenanceItem] = Field(
        default_factory=list, description="Internal traceability mapping statements to source agents."
    )
    error_type: Optional[str] = Field(default=None, description="Internal structured error category if failed.")
    error: Optional[str] = Field(default=None, description="Safe internal error description if failed.")
    retryable: Optional[bool] = Field(default=None, description="Whether the failure is retryable.")


class SynthesizerOutput(BaseModel):
    """
    Backward-compatible output model that wraps and projects SynthesizerResult.
    """
    status: str = Field(default="completed", description="Execution status.")
    final_answer: str = Field(..., description="User-facing final response.")
    key_decisions: List[KeyDecision] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    unresolved_conflicts: List[UnresolvedConflict] = Field(default_factory=list)
    synthesizer_result: Optional[SynthesizerResult] = Field(None, description="Full canonical Synthesizer result.")

    @classmethod
    def from_synthesizer_result(cls, result: SynthesizerResult) -> "SynthesizerOutput":
        """Project a canonical SynthesizerResult into SynthesizerOutput."""
        return cls(
            status=result.status.value if isinstance(result.status, AgentStatus) else str(result.status),
            final_answer=result.final_answer,
            key_decisions=result.key_decisions,
            limitations=result.limitations,
            unresolved_conflicts=result.unresolved_conflicts,
            synthesizer_result=result,
        )
