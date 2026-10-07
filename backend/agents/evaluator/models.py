from pydantic import BaseModel
from typing import Dict, List

class EvaluatorOutput(BaseModel):
    detected_contradictions: list[str]
    incompatible_assumptions: list[str]
    requirement_coverage_issues: list[str]
    unsupported_claims: list[str]
    missing_evidence: list[str]
    recommendations: list[str]
