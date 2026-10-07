from pydantic import BaseModel
from typing import Dict, List

class ResearcherOutput(BaseModel):
    users_and_needs: list[str]
    constraints: list[str]
    assumptions: list[str]
    missing_information: list[str]
    verified_evidence: list[str]
    source_references: list[str]
