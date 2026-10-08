from typing import Literal, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator
from backend.agents.researcher.models import ResearchResult
from backend.agents.strategist.models import StrategyResult


class SecurityInput(BaseModel):
    """
    Input contract for the Security Agent.
    Evaluates technical security risks based on the problem statement and any upstream
    research, strategy, or engineering specifications provided.
    """
    problem: str = Field(description="The problem statement to evaluate for technical security risks")
    context: Optional[Union[str, dict]] = Field(default=None, description="Optional domain or contextual background")
    research: Optional[ResearchResult] = Field(default=None, description="Optional structured research findings")
    strategy: Optional[StrategyResult] = Field(default=None, description="Optional strategic roadmap and priorities")
    engineering: Optional[Any] = Field(default=None, description="Optional engineering architecture or implementation details")

    @field_validator("problem")
    @classmethod
    def validate_problem_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Problem statement cannot be empty.")
        return v.strip()


import json

class SecurityResult(BaseModel):
    """
    Structured output contract for the Security Agent.
    Encapsulates defensive technical security assessment, threat modeling, attack surfaces,
    severity evaluations, and technical mitigations.
    """
    agent: Literal["security"] = Field(
        default="security",
        description="Exact canonical machine identifier. MUST be exactly 'security'."
    )
    status: Literal["completed", "failed"] = Field(
        default="completed",
        description="Execution status ('completed' or 'failed')."
    )

    @field_validator("agent", mode="before")
    @classmethod
    def _coerce_agent_identifier(cls, v: Any) -> str:
        if isinstance(v, str):
            clean = v.strip().lower()
            if clean in ("security", "security agent", "security_agent"):
                return "security"
        return v

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> str:
        if isinstance(v, str):
            clean = v.strip().lower()
            if clean in ("completed", "success", "ok"):
                return "completed"
            if clean in ("failed", "failure", "error"):
                return "failed"
        return v

    security_summary: str = Field(
        default="",
        description="High-level technical security assessment summary"
    )
    attack_surfaces: list[str] = Field(
        default_factory=list,
        description="Identified attack vectors and exposed entry points"
    )
    threats: list[str] = Field(
        default_factory=list,
        description="Core technical security threats identified"
    )
    authentication_risks: list[str] = Field(
        default_factory=list,
        description="Identified authentication and credential weaknesses"
    )
    authorization_risks: list[str] = Field(
        default_factory=list,
        description="Identified access control and privilege escalation risks"
    )
    data_privacy_risks: list[str] = Field(
        default_factory=list,
        description="Data leakage, PII exposure, and storage vulnerabilities"
    )
    api_security_risks: list[str] = Field(
        default_factory=list,
        description="Insecure endpoints, lack of rate-limiting, injection vectors"
    )
    prompt_injection_risks: list[str] = Field(
        default_factory=list,
        description="Risks from untrusted prompt or retrieval input manipulation"
    )
    secret_exposure_risks: list[str] = Field(
        default_factory=list,
        description="Hardcoded secrets, key leakage, or insecure env configs"
    )
    severity_levels: list[str] = Field(
        default_factory=list,
        description="Evaluated severity ratings (e.g. Critical, High, Medium, Low)"
    )
    mitigations: list[str] = Field(
        default_factory=list,
        description="Practical, prioritized technical countermeasures and controls"
    )
    security_assumptions: list[str] = Field(
        default_factory=list,
        description="Defensive assumptions made about the architecture"
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Scope limitations of this automated assessment"
    )

    @field_validator(
        "attack_surfaces",
        "threats",
        "authentication_risks",
        "authorization_risks",
        "data_privacy_risks",
        "api_security_risks",
        "prompt_injection_risks",
        "secret_exposure_risks",
        "mitigations",
        "security_assumptions",
        "limitations",
        mode="before",
    )
    @classmethod
    def _coerce_str_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, dict):
            parts = []
            for k in ("threat", "risk", "name", "title", "description", "summary", "mitigation"):
                if k in v and v[k]:
                    parts.append(str(v[k]))
            return parts if parts else [json.dumps(v)]
        if isinstance(v, (list, tuple)):
            result: list[str] = []
            for item in v:
                if isinstance(item, str):
                    if item.strip():
                        result.append(item.strip())
                elif isinstance(item, dict):
                    desc = item.get("threat") or item.get("name") or item.get("risk") or item.get("title") or item.get("mitigation") or item.get("description")
                    details = []
                    if desc:
                        details.append(str(desc))
                    if item.get("severity"):
                        details.append(f"Severity: {item['severity']}")
                    if item.get("impact"):
                        details.append(f"Impact: {item['impact']}")
                    if item.get("mitigation") and "mitigation" not in str(desc).lower():
                        details.append(f"Mitigation: {item['mitigation']}")
                    if details:
                        result.append(" - ".join(details))
                    else:
                        result.append(json.dumps(item))
                elif item is not None:
                    result.append(str(item))
            return result
        return [str(v)]

    @field_validator("severity_levels", mode="before")
    @classmethod
    def _coerce_severity(cls, v: Any) -> list[str]:
        valid_ratings = {"critical", "high", "medium", "low", "info", "informational"}
        if isinstance(v, dict):
            found: set[str] = set()
            for k, val in v.items():
                if str(k).strip().lower() in valid_ratings:
                    found.add(str(k).strip().title())
                if isinstance(val, str) and val.strip().lower() in valid_ratings:
                    found.add(val.strip().title())
                elif isinstance(val, list):
                    for sub in val:
                        if isinstance(sub, str) and sub.strip().lower() in valid_ratings:
                            found.add(sub.strip().title())
            if found:
                return sorted(list(found))
            return [f"{k}: {val}" for k, val in v.items()]
        return cls._coerce_str_list(v)


# Backward compatibility alias
SecurityOutput = SecurityResult
