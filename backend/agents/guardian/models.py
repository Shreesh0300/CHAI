from pydantic import BaseModel
from typing import Dict, List

class GuardianOutput(BaseModel):
    safety_and_privacy_risks: list[str]
    reliability_and_ethical_risks: list[str]
    unsafe_assumptions: list[str]
    limitations: list[str]
    recommended_mitigations: list[str]
