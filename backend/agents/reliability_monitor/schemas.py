"""
Structured Pydantic schemas for the CHAI Reliability Monitor Agent.

The Reliability Monitor is the final reasoning-quality and trust-assessment
checkpoint in CHAI, evaluating execution completeness, evidence grounding,
internal consistency, conflict status, provenance, assumptions, missing information,
unsupported claims, and overconfidence across observable workflow signals.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class AgentStatus(str, Enum):
    """Controlled execution status for the Reliability Monitor Agent."""
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ReliabilityLevel(str, Enum):
    """Qualitative classification of overall workflow reliability."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ReliabilityAction(str, Enum):
    """Downstream gate decision recommendation for CHAI."""
    PROCEED = "PROCEED"
    PROCEED_WITH_LIMITATIONS = "PROCEED_WITH_LIMITATIONS"
    REQUEST_MORE_INFORMATION = "REQUEST_MORE_INFORMATION"
    BLOCK_OUTPUT = "BLOCK_OUTPUT"


class DimensionStatus(str, Enum):
    """Status assessment for an individual reliability dimension."""
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class ReliabilityDimension(BaseModel):
    """Evaluation of a specific reliability dimension with score, status, and evidence."""
    name: str = Field(..., description="Name of the reliability dimension.")
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized dimension score (0.0 to 1.0).")
    weight: float = Field(default=0.125, ge=0.0, le=1.0, description="Dimension weighting factor.")
    status: DimensionStatus = Field(default=DimensionStatus.PASSED, description="Evaluation status.")
    reason: str = Field(..., description="Explainable rationale grounded in workflow signals.")
    evidence: Optional[str] = Field(None, description="Specific supporting evidence from workflow context.")


class UnsupportedClaimFinding(BaseModel):
    """An assertion in the synthesized answer lacking adequate evidentiary support."""
    claim: str = Field(..., description="The unsupported statement or statistic.")
    reason: str = Field(..., description="Why the claim lacks backing in the supplied context.")
    severity: str = Field(default="medium", description="Severity rating: 'low', 'medium', or 'high'.")


class ReliabilityMonitorResult(BaseModel):
    """
    Canonical structured output of the CHAI Reliability Monitor Agent.

    Contains explainable reliability score, qualitative level, gate action,
    evaluated dimensions, detected concerns, unsupported claims, and limitations.
    """
    agent: str = Field(default="reliability_monitor", description="Agent identifier.")
    status: AgentStatus = Field(default=AgentStatus.COMPLETED, description="Execution status.")

    reliability_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Explainable aggregate reliability score (0.0 to 1.0)."
    )
    reliability_level: ReliabilityLevel = Field(
        default=ReliabilityLevel.UNKNOWN, description="Qualitative reliability category (HIGH, MEDIUM, LOW)."
    )
    action: ReliabilityAction = Field(
        default=ReliabilityAction.PROCEED_WITH_LIMITATIONS,
        description="Gate decision recommendation for CHAI.",
    )

    dimensions: List[ReliabilityDimension] = Field(
        default_factory=list, description="Structured evaluations across key reliability dimensions."
    )
    strengths: List[str] = Field(
        default_factory=list, description="Verified strong aspects of the workflow outcome."
    )
    concerns: List[str] = Field(
        default_factory=list, description="Specific reliability concerns identified from workflow signals."
    )
    failed_agents: List[str] = Field(
        default_factory=list, description="Agents that failed or were unavailable during execution."
    )
    unresolved_conflicts: List[str] = Field(
        default_factory=list, description="Open disagreements not resolved prior to synthesis."
    )
    unsupported_claims: List[UnsupportedClaimFinding] = Field(
        default_factory=list, description="Specific claims in final answer lacking backing findings."
    )
    evidence_gaps: List[str] = Field(
        default_factory=list, description="Critical evidence missing from the collective findings."
    )
    assumptions: List[str] = Field(
        default_factory=list, description="Transparent assumptions noted in the workflow."
    )
    missing_information: List[str] = Field(
        default_factory=list, description="Material information missing from user context."
    )
    provenance_quality: Optional[str] = Field(
        None, description="Assessment of traceability linking conclusions to source agents."
    )
    execution_completeness: Optional[str] = Field(
        None, description="Assessment of pipeline stage execution completeness."
    )
    overconfidence_detected: bool = Field(
        default=False, description="Whether final answer language exceeds evidentiary backing."
    )
    limitations: List[str] = Field(
        default_factory=list, description="Limitations that should accompany the final answer."
    )
    recommendation: Optional[str] = Field(
        None, description="Actionable recommendation for downstream output handling."
    )

    @field_validator(
        "strengths",
        "concerns",
        "failed_agents",
        "unresolved_conflicts",
        "evidence_gaps",
        "assumptions",
        "missing_information",
        "limitations",
        mode="before",
    )
    @classmethod
    def _coerce_str_list(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, (list, tuple)):
            return [str(item) for item in v]
        return [str(v)]

    @model_validator(mode="before")
    @classmethod
    def _validate_payload_structure(cls, data: Any) -> Any:
        if isinstance(data, dict) and data:
            recognized = {
                "agent",
                "status",
                "reliability_score",
                "reliability_level",
                "action",
                "dimensions",
                "strengths",
                "concerns",
                "failed_agents",
                "unresolved_conflicts",
                "unsupported_claims",
                "evidence_gaps",
                "assumptions",
                "missing_information",
                "provenance_quality",
                "execution_completeness",
                "overconfidence_detected",
                "limitations",
                "recommendation",
            }
            if not any(k in recognized for k in data.keys()):
                raise ValueError("Payload contains no recognized ReliabilityMonitorResult fields.")
        return data


class ReliabilityMonitorOutput(BaseModel):
    """
    Backward-compatible wrapper model for the Reliability Monitor Agent.

    Projects core score, level, action, and concerns while embedding the full
    canonical ReliabilityMonitorResult.
    """
    status: str = Field(default="completed", description="Execution status.")
    reliability_score: Optional[float] = Field(None, description="Reliability score.")
    reliability_level: str = Field(default="UNKNOWN", description="Qualitative level.")
    action: str = Field(default="PROCEED_WITH_LIMITATIONS", description="Gate action.")
    concerns: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    reliability_monitor_result: Optional[ReliabilityMonitorResult] = Field(
        None, description="Full canonical ReliabilityMonitorResult."
    )

    @classmethod
    def from_reliability_monitor_result(
        cls, result: ReliabilityMonitorResult
    ) -> "ReliabilityMonitorOutput":
        """Project a canonical ReliabilityMonitorResult into ReliabilityMonitorOutput."""
        return cls(
            status=result.status.value if isinstance(result.status, AgentStatus) else str(result.status),
            reliability_score=result.reliability_score,
            reliability_level=result.reliability_level.value if isinstance(result.reliability_level, ReliabilityLevel) else str(result.reliability_level),
            action=result.action.value if isinstance(result.action, ReliabilityAction) else str(result.action),
            concerns=result.concerns,
            limitations=result.limitations,
            reliability_monitor_result=result,
        )
