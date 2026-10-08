"""
Structured Pydantic schemas for the CHAI Conflict Resolver Agent.

The Conflict Resolver arbitrates cross-agent disagreements detected by Evaluator,
prioritizing explicit user requirements, safety and security boundaries, and
empirical evidence, while transparently preserving unresolved conflicts.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class AgentStatus(str, Enum):
    """Controlled execution status for the Conflict Resolver Agent."""
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class Resolution(BaseModel):
    """An explicit arbitration decision resolving a specific conflict."""
    conflict: str = Field(..., description="Summary of the conflict or trade-off being resolved.")
    decision: str = Field(..., description="The explicit arbitration decision.")
    preferred_option: str = Field(..., description="The option or path chosen.")
    reason: str = Field(..., description="Justification grounded in requirements, safety, or evidence.")
    decision_basis: List[str] = Field(
        default_factory=list,
        description="Specific principles, requirements, or evidence supporting the decision.",
    )
    supporting_agents: List[str] = Field(
        default_factory=list,
        description="Agents whose findings support this preferred option.",
    )
    position_a: Optional[str] = Field(
        None,
        description="What one agent or perspective recommends.",
    )
    position_b: Optional[str] = Field(
        None,
        description="What another agent or perspective recommends.",
    )
    why_they_differ: Optional[str] = Field(
        None,
        description="Underlying assumption or evidence explaining why they differ.",
    )
    rationale: Optional[str] = Field(
        None,
        description="Evidence or requirements supporting the resolution.",
    )
    resolution: Optional[str] = Field(
        None,
        description="Convenience composite resolution text.",
    )

    @field_validator("decision_basis", "supporting_agents", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, (list, tuple)):
            return [str(item) for item in v]
        return [str(v)]

    @model_validator(mode="after")
    def _populate_composite_resolution(self) -> "Resolution":
        if not self.rationale and self.reason:
            self.rationale = self.reason
        if not self.resolution:
            if self.position_a and self.position_b:
                parts = [
                    f"CONFLICT: {self.conflict}",
                    f"POSITION A: {self.position_a}",
                    f"POSITION B: {self.position_b}",
                ]
                if self.why_they_differ:
                    parts.append(f"WHY THEY DIFFER: {self.why_they_differ}")
                parts.append(f"RESOLUTION: {self.decision}")
                if self.rationale:
                    parts.append(f"RATIONALE: {self.rationale}")
                self.resolution = "\n".join(parts)
            else:
                self.resolution = f"{self.decision}: {self.reason}"
        return self


class UnresolvedConflictItem(BaseModel):
    """A conflict that cannot be safely or reliably resolved with available information."""
    conflict: str = Field(..., description="Description of the conflict that cannot currently be resolved.")
    reason: str = Field(..., description="Why the conflict cannot be safely or reliably resolved.")
    missing_information: List[str] = Field(
        default_factory=list,
        description="Information or clarification needed to resolve the conflict.",
    )
    impact: Optional[str] = Field(
        None,
        description="Potential impact or trade-off of leaving this conflict open.",
    )
    reason_unresolved: Optional[str] = Field(
        None,
        description="Alias for reason, matching downstream Synthesizer expectations.",
    )

    @field_validator("missing_information", mode="before")
    @classmethod
    def _coerce_missing_info(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, (list, tuple)):
            return [str(item) for item in v]
        return [str(v)]

    @model_validator(mode="after")
    def _sync_reason_unresolved(self) -> "UnresolvedConflictItem":
        if not self.reason_unresolved:
            self.reason_unresolved = self.reason
        return self


class ProvenanceItem(BaseModel):
    """Traceability mapping linking arbitration decisions to participating agents."""
    statement: str = Field(..., description="Key arbitration conclusion or statement.")
    supported_by: List[str] = Field(
        default_factory=list,
        description="Participating agents supporting this statement.",
    )

    @field_validator("supported_by", mode="before")
    @classmethod
    def _coerce_supported_by(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, (list, tuple)):
            return [str(item) for item in v]
        return [str(v)]


class ConflictResolutionResult(BaseModel):
    """
    Canonical structured output of the CHAI Conflict Resolver Agent.

    Contains explicit resolutions, unresolved conflicts, decision basis,
    assumptions, missing information, limitations, and provenance.
    """
    agent: str = Field(default="conflict_resolver", description="Agent identifier.")
    status: AgentStatus = Field(default=AgentStatus.COMPLETED, description="Execution status.")

    resolutions: List[Resolution] = Field(
        default_factory=list,
        description="Explicit arbitration decisions for resolvable conflicts.",
    )
    unresolved_conflicts: List[UnresolvedConflictItem] = Field(
        default_factory=list,
        description="Conflicts that cannot currently be decided due to missing info or hard trade-offs.",
    )
    decision_basis: List[str] = Field(
        default_factory=list,
        description="High-level principles and priorities applied during arbitration.",
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Assumptions accepted or clarified during conflict resolution.",
    )
    missing_information: List[str] = Field(
        default_factory=list,
        description="Information missing that prevented stronger resolution.",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Limitations and constraints of the arbitration outcome.",
    )
    conflicts_considered: List[str] = Field(
        default_factory=list,
        description="Summary list of all conflict areas evaluated.",
    )
    provenance: List[ProvenanceItem] = Field(
        default_factory=list,
        description="Traceability linking resolutions to contributing agents.",
    )

    # Downstream compatibility fields
    conflict: Optional[str] = Field(
        None,
        description="Primary conflict summary for backward-compatible consumer dicts.",
    )
    resolution: Optional[str] = Field(
        None,
        description="Primary resolution summary for backward-compatible consumer dicts.",
    )
    reason_unresolved: Optional[str] = Field(
        None,
        description="Primary unresolved reason for backward-compatible consumer dicts.",
    )

    @field_validator("decision_basis", "assumptions", "missing_information", "limitations", "conflicts_considered", mode="before")
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
                "resolutions",
                "unresolved_conflicts",
                "decision_basis",
                "assumptions",
                "missing_information",
                "limitations",
                "conflicts_considered",
                "provenance",
                "conflict",
                "resolution",
                "reason_unresolved",
            }
            if not any(k in recognized for k in data.keys()):
                raise ValueError("Payload contains no recognized ConflictResolutionResult fields.")
        return data

    @model_validator(mode="after")
    def _populate_legacy_fields(self) -> "ConflictResolutionResult":
        if self.resolutions:
            if not self.conflict:
                self.conflict = self.resolutions[0].conflict
            if not self.resolution:
                r0 = self.resolutions[0]
                self.resolution = f"Prefer {r0.preferred_option}: {r0.reason}"
        elif self.unresolved_conflicts:
            if not self.conflict:
                self.conflict = self.unresolved_conflicts[0].conflict
            if not self.reason_unresolved:
                self.reason_unresolved = self.unresolved_conflicts[0].reason
        else:
            if not self.conflict:
                self.conflict = "No material conflict detected."
            if not self.resolution:
                self.resolution = "No material conflict detected."
        return self


class ConflictResolverOutput(BaseModel):
    """
    Backward-compatible wrapper model for the Conflict Resolver Agent.

    Exposes top-level status, resolutions, and unresolved conflicts while embedding
    the full canonical ConflictResolutionResult.
    """
    status: str = Field(default="completed", description="Execution status.")
    resolutions: List[Resolution] = Field(default_factory=list)
    unresolved_conflicts: List[UnresolvedConflictItem] = Field(default_factory=list)
    decision_basis: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    conflict_resolution_result: Optional[ConflictResolutionResult] = Field(
        None, description="Full canonical ConflictResolutionResult."
    )

    @classmethod
    def from_conflict_resolution_result(
        cls, result: ConflictResolutionResult
    ) -> "ConflictResolverOutput":
        """Project a canonical ConflictResolutionResult into ConflictResolverOutput."""
        return cls(
            status=result.status.value if isinstance(result.status, AgentStatus) else str(result.status),
            resolutions=result.resolutions,
            unresolved_conflicts=result.unresolved_conflicts,
            decision_basis=result.decision_basis,
            limitations=result.limitations,
            conflict_resolution_result=result,
        )
