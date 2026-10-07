"""
Structured Pydantic schemas for the CHAI Guardian Agent.

These schemas define the contract for the Guardian Agent (safety, ethics,
privacy, misuse, human oversight, user vulnerability, transparency,
responsible-use guidelines, and safeguards).
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


class RiskLevel(str, Enum):
    """Controlled overall risk levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskItem(BaseModel):
    """A structured safety or ethical risk item."""
    risk: str = Field(..., description="Description of the risk.")
    category: str = Field(..., description="Category (e.g., 'safety', 'ethical', 'privacy', 'misuse').")
    severity: RiskLevel = Field(default=RiskLevel.MEDIUM, description="Severity of the risk.")
    likelihood: Optional[str] = Field(None, description="Likelihood of occurrence (low, medium, high).")
    impact: Optional[str] = Field(None, description="Potential real-world impact if the risk materializes.")
    mitigation: Optional[str] = Field(None, description="Recommended safeguard or mitigation strategy.")


class HumanOversight(BaseModel):
    """Human oversight requirements."""
    required: bool = Field(default=False, description="Whether human oversight is recommended or required.")
    reason: str = Field(..., description="Reasoning for the oversight requirement level.")
    recommended_mechanism: Optional[str] = Field(
        None,
        description="Recommended human-in-the-loop mechanism (e.g., clinician review, appeal path, supervisor sign-off)."
    )


class UserVulnerability(BaseModel):
    """Considerations for vulnerable populations."""
    vulnerable_populations_identified: List[str] = Field(
        default_factory=list,
        description="Vulnerable groups identified (e.g. children, elderly, patients, financially distressed)."
    )
    concerns: List[str] = Field(default_factory=list, description="Specific safety/ethical concerns for these populations.")
    safeguards: List[str] = Field(default_factory=list, description="Tailored safeguards to protect vulnerable users.")


class GuardianResult(BaseModel):
    """
    The canonical structured output of the CHAI Guardian Agent.

    Consumed by downstream agents (Coordinator, Evaluator, Synthesizer, Conflict Resolver).
    """
    agent: str = Field(default="guardian", description="Agent identifier.")
    status: AgentStatus = Field(default=AgentStatus.COMPLETED, description="Execution status.")

    safety_assessment: str = Field(..., description="Overall high-level safety and responsible-use assessment.")
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Overall risk level (low, medium, high, critical).")

    safety_risks: List[RiskItem] = Field(default_factory=list, description="Safety risks identified.")
    ethical_risks: List[RiskItem] = Field(default_factory=list, description="Ethical risks (bias, fairness, discrimination, autonomy).")
    privacy_considerations: List[str] = Field(default_factory=list, description="Privacy implications and principles.")
    misuse_risks: List[str] = Field(default_factory=list, description="Realistic misuse and abuse scenarios.")

    human_oversight: Optional[HumanOversight] = Field(None, description="Human oversight requirements.")
    user_vulnerability: Optional[UserVulnerability] = Field(None, description="Vulnerable user considerations.")
    transparency_requirements: List[str] = Field(default_factory=list, description="Transparency and disclosure requirements.")
    safeguards: List[str] = Field(default_factory=list, description="Key safeguards and safety mitigations.")
    responsible_use_guidelines: List[str] = Field(default_factory=list, description="Actionable responsible-use guidelines.")

    assumptions: List[str] = Field(default_factory=list, description="Safety-related assumptions made by the agent.")
    missing_information: List[str] = Field(default_factory=list, description="Safety-critical information missing from the query.")


class GuardianOutput(BaseModel):
    """
    Backward-compatible output model consumed by the Coordinator.

    Projects ``GuardianResult`` into the original fields expected by
    ``backend/core/coordinator.py`` while embedding the full ``GuardianResult``.
    """
    safety_and_privacy_risks: List[str] = Field(default_factory=list)
    reliability_and_ethical_risks: List[str] = Field(default_factory=list)
    unsafe_assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    recommended_mitigations: List[str] = Field(default_factory=list)

    guardian_result: Optional[GuardianResult] = Field(None, description="Full canonical Guardian analysis.")

    @classmethod
    def from_guardian_result(cls, result: GuardianResult) -> "GuardianOutput":
        """Project a canonical ``GuardianResult`` into the backward-compatible shape."""
        # Safety & privacy risks
        sp_risks: List[str] = [
            f"[{r.severity.value.upper()}] {r.risk}" for r in result.safety_risks
        ]
        for p in result.privacy_considerations:
            sp_risks.append(f"[PRIVACY] {p}")

        # Reliability & ethical risks
        re_risks: List[str] = [
            f"[{r.severity.value.upper()}] {r.risk}" for r in result.ethical_risks
        ]
        for m in result.misuse_risks:
            re_risks.append(f"[MISUSE] {m}")

        # Unsafe assumptions
        unsafe_assumptions = list(result.assumptions)

        # Limitations (missing information + transparency requirements)
        limitations = list(result.missing_information)
        for t in result.transparency_requirements:
            limitations.append(f"[TRANSPARENCY] {t}")

        # Recommended mitigations (safeguards + guidelines + risk mitigations)
        mitigations = list(result.safeguards)
        for g in result.responsible_use_guidelines:
            if g not in mitigations:
                mitigations.append(g)
        for r in result.safety_risks + result.ethical_risks:
            if r.mitigation and r.mitigation not in mitigations:
                mitigations.append(r.mitigation)
        if result.human_oversight and result.human_oversight.required:
            oversight_text = f"Human oversight required: {result.human_oversight.reason}"
            if oversight_text not in mitigations:
                mitigations.append(oversight_text)

        return cls(
            safety_and_privacy_risks=sp_risks,
            reliability_and_ethical_risks=re_risks,
            unsafe_assumptions=unsafe_assumptions,
            limitations=limitations,
            recommended_mitigations=mitigations,
            guardian_result=result,
        )
