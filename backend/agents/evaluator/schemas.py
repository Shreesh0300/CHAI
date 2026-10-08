

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    """Controlled status values for agent execution."""
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class EvaluationSeverity(str, Enum):
    """Severity ratings for conflicts, inconsistencies, and quality issues."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RequirementStatus(str, Enum):
    """Evaluation status for a given requirement."""
    ADDRESSED = "addressed"
    PARTIALLY_ADDRESSED = "partially_addressed"
    NOT_ADDRESSED = "not_addressed"
    UNCLEAR = "unclear"


class RequirementCoverageItem(BaseModel):
    """Evaluation of whether a specific requirement is addressed across agent outputs."""
    requirement: str = Field(..., description="The user or technical requirement under evaluation.")
    status: RequirementStatus = Field(..., description="Coverage status of this requirement.")
    evidence: Optional[str] = Field(None, description="Where and how the requirement is addressed in agent outputs.")
    gap: Optional[str] = Field(None, description="What is missing, unaddressed, or ambiguous.")


class ConflictItem(BaseModel):
    """A detected conflict or disagreement between two or more agent perspectives."""
    conflict: str = Field(..., description="Summary of the conflict or disagreement.")
    agents_involved: List[str] = Field(default_factory=list, description="Agents expressing conflicting perspectives.")
    severity: EvaluationSeverity = Field(default=EvaluationSeverity.MEDIUM, description="Severity of the conflict.")
    evidence: Optional[str] = Field(None, description="Specific statements or citations demonstrating the conflict.")
    impact: Optional[str] = Field(None, description="Potential real-world impact if this conflict is unresolved.")
    recommendation: Optional[str] = Field(None, description="Actionable recommendation for reconciling this conflict.")


class InconsistencyItem(BaseModel):
    """A logical contradiction or incompatible statements within or across agent outputs."""
    statements: List[str] = Field(default_factory=list, description="The contradictory statements identified.")
    source_agents: List[str] = Field(default_factory=list, description="Agents where the incompatible statements originate.")
    issue: str = Field(..., description="Why these statements are logically contradictory or incompatible.")
    severity: EvaluationSeverity = Field(default=EvaluationSeverity.MEDIUM, description="Severity of the inconsistency.")
    recommendation: Optional[str] = Field(None, description="How the contradiction should be resolved.")


class UnsupportedClaimItem(BaseModel):
    """A claim or assertion made without sufficient justification or supporting evidence."""
    claim: str = Field(..., description="The assertion lacking evidentiary backing.")
    source_agent: str = Field(..., description="Agent that made the unsupported claim.")
    issue: str = Field(..., description="Why the claim is considered unsupported or insufficiently justified.")
    severity: EvaluationSeverity = Field(default=EvaluationSeverity.LOW, description="Significance of the claim's lack of support.")
    recommendation: Optional[str] = Field(None, description="Recommended verification or evidence requirement.")


class QualityIssueItem(BaseModel):
    """A quality defect, missing constraint, or weakness identified in the collective outputs."""
    issue: str = Field(..., description="Description of the quality issue.")
    category: str = Field(..., description="Category (e.g. 'completeness', 'justification', 'over-engineering', 'dependency').")
    impact: Optional[str] = Field(None, description="Potential impact on solution viability.")
    recommendation: Optional[str] = Field(None, description="Recommended remediation.")


class EvaluatorResult(BaseModel):
    """
    The canonical structured output of the CHAI Evaluator Agent.

    Consumed by downstream agents (Coordinator, Conflict Resolver, Synthesizer).
    """
    agent: str = Field(default="evaluator", description="Agent identifier.")
    status: AgentStatus = Field(default=AgentStatus.COMPLETED, description="Execution status.")

    overall_assessment: str = Field(..., description="High-level evaluation synthesis of the combined agent outputs.")

    requirement_coverage: List[RequirementCoverageItem] = Field(
        default_factory=list, description="Analysis of requirement coverage across agent outputs."
    )
    conflicts: List[ConflictItem] = Field(
        default_factory=list, description="Cross-agent conflicts and disagreements."
    )
    inconsistencies: List[InconsistencyItem] = Field(
        default_factory=list, description="Logical contradictions and incompatible assumptions."
    )
    unsupported_claims: List[UnsupportedClaimItem] = Field(
        default_factory=list, description="Claims lacking sufficient evidence or justification."
    )
    quality_issues: List[QualityIssueItem] = Field(
        default_factory=list, description="Identified quality defects and analytical gaps."
    )
    strengths: List[str] = Field(
        default_factory=list, description="Strengths and well-supported aspects of the combined perspectives."
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Actionable recommendations for improvement and reconciliation."
    )
    assumptions: List[str] = Field(
        default_factory=list, description="Evaluator assumptions regarding requirements or context."
    )
    missing_information: List[str] = Field(
        default_factory=list, description="Critical information missing from the collective agent outputs."
    )


class EvaluatorOutput(BaseModel):
    """
    Backward-compatible output model consumed by the Coordinator.

    Projects ``EvaluatorResult`` into the attributes expected by
    ``backend/core/coordinator.py`` (specifically ``detected_contradictions``
    and standard list fields) while embedding the full canonical ``EvaluatorResult``.
    """
    detected_contradictions: List[str] = Field(default_factory=list)
    incompatible_assumptions: List[str] = Field(default_factory=list)
    requirement_coverage_issues: List[str] = Field(default_factory=list)
    unsupported_claims: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)

    evaluator_result: Optional[EvaluatorResult] = Field(None, description="Full canonical Evaluator analysis.")

    @classmethod
    def from_evaluator_result(cls, result: EvaluatorResult) -> "EvaluatorOutput":
        """Project a canonical ``EvaluatorResult`` into the backward-compatible shape."""
        # detected_contradictions: conflicts + inconsistencies
        contradictions: List[str] = []
        for c in result.conflicts:
            agents = f"[{', '.join(c.agents_involved)}]" if c.agents_involved else ""
            contradictions.append(f"Conflict {agents}: {c.conflict} (Severity: {c.severity.value})")
        for inc in result.inconsistencies:
            contradictions.append(f"Inconsistency: {inc.issue} (Severity: {inc.severity.value})")

        # incompatible_assumptions: from assumptions and quality issues
        incompatible_assumptions: List[str] = list(result.assumptions)
        for qi in result.quality_issues:
            if "assumption" in qi.category.lower() or "assumption" in qi.issue.lower():
                incompatible_assumptions.append(f"{qi.category}: {qi.issue}")

        # requirement_coverage_issues: not_addressed, partially_addressed, unclear
        req_issues: List[str] = []
        for req in result.requirement_coverage:
            if req.status != RequirementStatus.ADDRESSED:
                gap_text = f" — Gap: {req.gap}" if req.gap else ""
                req_issues.append(f"[{req.status.value.upper()}] {req.requirement}{gap_text}")

        # unsupported_claims
        unsupported: List[str] = [
            f"[{u.source_agent}] {u.claim} (Issue: {u.issue})" for u in result.unsupported_claims
        ]

        # missing_evidence: missing_information + evidentiary gaps
        missing_ev: List[str] = list(result.missing_information)
        for req in result.requirement_coverage:
            if req.status == RequirementStatus.UNCLEAR and req.requirement not in missing_ev:
                missing_ev.append(f"Unclear evidence for requirement: {req.requirement}")

        # recommendations
        recs: List[str] = list(result.recommendations)
        for c in result.conflicts:
            if c.recommendation and c.recommendation not in recs:
                recs.append(c.recommendation)
        for inc in result.inconsistencies:
            if inc.recommendation and inc.recommendation not in recs:
                recs.append(inc.recommendation)

        return cls(
            detected_contradictions=contradictions,
            incompatible_assumptions=incompatible_assumptions,
            requirement_coverage_issues=req_issues,
            unsupported_claims=unsupported,
            missing_evidence=missing_ev,
            recommendations=recs,
            evaluator_result=result,
        )
