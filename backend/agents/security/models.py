from pydantic import BaseModel
from typing import Dict, List

class SecurityOutput(BaseModel):
    threats_and_attack_surfaces: list[str]
    auth_and_privacy_issues: list[str]
    prompt_injection_risks: list[str]
    insecure_api_access: list[str]
    recommended_mitigations: list[str]
    severity_levels: dict[str, str]
