from pydantic import BaseModel
from typing import Dict, List

class EngineerOutput(BaseModel):
    technical_architecture: str
    recommended_technologies: list[str]
    components_and_apis: list[str]
    data_flow: str
    implementation_plan: list[str]
