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


class SecurityResult(BaseModel):
    """
    Structured output contract for the Security Agent.
    Encapsulates defensive technical security assessment, threat modeling, attack surfaces,
    severity evaluations, and technical mitigations.
    """
    agent: Literal["security"] = "security"
    status: Literal["completed", "failed"] = "completed"

    @field_validator("agent", mode="before")
    @classmethod
    def normalize_agent(cls, v: Any) -> Any:
        if isinstance(v, str) and v.lower().strip() in ("security", "security agent"):
            return "security"
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
        "threats",
        "attack_surfaces",
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
    def normalize_string_list_fields(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, str):
                    if item.strip():
                        res.append(item.strip())
                elif isinstance(item, dict):
                    desc = (
                        item.get("vector")
                        or item.get("threat")
                        or item.get("description")
                        or item.get("risk")
                        or item.get("mitigation")
                        or ": ".join(f"{k}: {val}" for k, val in item.items() if val)
                    )
                    if desc:
                        res.append(str(desc).strip())
                elif isinstance(item, (int, float)):
                    res.append(str(item))
            return res
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        return v

    @field_validator("severity_levels", mode="before")
    @classmethod
    def normalize_severity_levels(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, str):
                    if item.strip():
                        res.append(item.strip())
                elif isinstance(item, (int, float)):
                    res.append(str(item))
                elif isinstance(item, dict):
                    for k, val in item.items():
                        res.append(f"{k}: {val}")
                else:
                    raise ValueError(f"Malformed item in severity_levels: {item}")
            return res
        if isinstance(v, dict):
            res = []
            for k, val in v.items():
                if not isinstance(k, str) or not isinstance(val, (str, int, float, list)):
                    raise ValueError(f"Malformed entry in severity_levels dict: {k}: {val}")
                if isinstance(val, list):
                    res.append(f"{k}: {', '.join(str(x) for x in val)}")
                else:
                    res.append(f"{k}: {val}")
            return res
        if isinstance(v, str):
            if not v.strip():
                return []
            return [part.strip() for part in v.split(",") if part.strip()]
        raise ValueError(f"Malformed severity_levels: expected list or dict, got {type(v).__name__}")


# Backward compatibility alias
SecurityOutput = SecurityResult
