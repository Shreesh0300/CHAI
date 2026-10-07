from pydantic import BaseModel
from typing import Dict, List

class StrategistOutput(BaseModel):
    strategy_overview: str
    prioritized_requirements: list[str]
    feasibility_and_tradeoffs: list[str]
    phased_execution_plan: list[str]
    success_criteria: list[str]
