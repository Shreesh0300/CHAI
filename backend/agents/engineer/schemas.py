"""
Structured Pydantic schemas for the CHAI Engineer Agent.

These schemas define the contract between the Engineer Agent and all
downstream consumers (Coordinator, Evaluator, Security Agent, Synthesizer,
Conflict Resolver).

Design principles:
- Structured sub-models where useful (risks, recommendations, APIs, etc.)
- Optional fields for sections that may not apply to every problem
- Stable field names for predictable downstream consumption
- Backward compatibility with coordinator's access to `technical_architecture`
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    """Controlled status values for agent execution."""
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Sub-models — structured building blocks
# ---------------------------------------------------------------------------

class ArchitectureLayer(BaseModel):
    """A single layer or tier in the system architecture."""
    name: str = Field(..., description="Layer name (e.g. 'Presentation', 'Application', 'Data').")
    description: str = Field(..., description="Purpose and responsibilities of this layer.")
    components: List[str] = Field(default_factory=list, description="Key components in this layer.")


class ArchitectureDesign(BaseModel):
    """Overall system architecture description."""
    overview: str = Field(default="Architecture overview", description="High-level architecture summary.")
    pattern: Optional[str] = Field(None, description="Architecture pattern (e.g. 'Layered', 'Microservices', 'Serverless').")
    layers: List[ArchitectureLayer] = Field(default_factory=list, description="Architecture layers/tiers.")
    relationships: List[str] = Field(default_factory=list, description="Key relationships between components.")

    @model_validator(mode="before")
    @classmethod
    def populate_overview(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("overview"):
            data["overview"] = data.get("summary") or data.get("description") or data.get("pattern") or "Architecture overview"
        return data


class TechnologyRecommendation(BaseModel):
    """A single technology recommendation with rationale."""
    technology: str = Field(..., description="Name of the technology or tool.")
    purpose: str = Field(..., description="What role this technology serves.")
    rationale: str = Field(..., description="Why this technology is recommended.")
    alternatives: List[str] = Field(default_factory=list, description="Reasonable alternative choices.")


class DataFlowStep(BaseModel):
    """A single step in the data flow."""
    source: str = Field(..., description="Where data originates in this step.")
    destination: str = Field(..., description="Where data goes in this step.")
    description: str = Field(..., description="What happens during this step.")


class APIEndpoint(BaseModel):
    """A recommended API endpoint."""
    method: str = Field(..., description="HTTP method (GET, POST, PUT, DELETE, etc.).")
    path: str = Field(..., description="Endpoint path (e.g. '/api/orders').")
    purpose: str = Field(..., description="What this endpoint does.")
    input_summary: Optional[str] = Field(None, description="Key input parameters or request body.")
    output_summary: Optional[str] = Field(None, description="Key output or response shape.")


class DatabaseEntity(BaseModel):
    """An important database entity."""
    name: str = Field(..., description="Entity/table name.")
    description: str = Field(..., description="Purpose of this entity.")
    important_fields: List[str] = Field(default_factory=list, description="Key fields/columns.")
    relationships: List[str] = Field(default_factory=list, description="Relationships to other entities.")


class DatabaseDesign(BaseModel):
    """Architecture-level database/storage design."""
    overview: str = Field(default="Database design overview", description="Storage strategy summary.")
    storage_type: Optional[str] = Field(None, description="Primary storage type (SQL, NoSQL, file, etc.).")
    entities: List[DatabaseEntity] = Field(default_factory=list, description="Important entities.")
    indexing_considerations: List[str] = Field(default_factory=list, description="Indexing notes.")

    @model_validator(mode="before")
    @classmethod
    def populate_overview(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("overview"):
            data["overview"] = data.get("summary") or data.get("description") or data.get("storage_type") or "Database design overview"
        return data


class AIMLDesign(BaseModel):
    """AI/ML architecture when applicable."""
    model_config = {"protected_namespaces": ()}

    overview: str = Field(default="AI/ML architecture overview", description="AI/ML role in the system.")
    model_role: Optional[str] = Field(None, description="What the model does.")
    inference_flow: Optional[str] = Field(None, description="How inference is performed.")
    model_selection: Optional[str] = Field(None, description="Model selection considerations.")
    data_pipeline: Optional[str] = Field(None, description="Data pipeline for training/inference.")
    rag_design: Optional[str] = Field(None, description="RAG architecture if applicable.")
    evaluation: Optional[str] = Field(None, description="Evaluation requirements.")
    latency_cost: Optional[str] = Field(None, description="Latency and cost considerations.")

    @model_validator(mode="before")
    @classmethod
    def populate_overview(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("overview"):
            data["overview"] = (
                data.get("model_role")
                or data.get("role")
                or data.get("description")
                or data.get("summary")
                or "AI/ML architecture overview"
            )
        return data


class TechnicalRisk(BaseModel):
    """A technical risk with impact and mitigation."""
    risk: str = Field(..., description="Description of the technical risk.")
    impact: str = Field(..., description="Potential impact if the risk materialises.")
    mitigation: str = Field(..., description="Recommended mitigation strategy.")


class Tradeoff(BaseModel):
    """An engineering tradeoff."""
    decision: str = Field(..., description="The decision area (e.g. 'Database selection').")
    options: List[str] = Field(default_factory=list, description="Available options.")
    comparison: str = Field(..., description="Brief comparison of the options.")
    recommendation: Optional[str] = Field(None, description="Recommended choice and why.")


class ImplementationPhase(BaseModel):
    """A phase in the implementation plan."""
    phase: str = Field(..., description="Phase name or number.")
    description: str = Field(..., description="What is delivered in this phase.")
    key_tasks: List[str] = Field(default_factory=list, description="Important tasks in this phase.")


class ScalabilityDesign(BaseModel):
    """Scalability considerations."""
    overview: str = Field(default="Scalability overview", description="Scalability strategy summary.")
    considerations: List[str] = Field(default_factory=list, description="Key scalability points.")

    @model_validator(mode="before")
    @classmethod
    def populate_overview(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("overview"):
            data["overview"] = data.get("summary") or data.get("description") or "Scalability overview"
        return data


class PerformanceDesign(BaseModel):
    """Performance considerations."""
    overview: str = Field(default="Performance overview", description="Performance strategy summary.")
    considerations: List[str] = Field(default_factory=list, description="Key performance points.")

    @model_validator(mode="before")
    @classmethod
    def populate_overview(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("overview"):
            data["overview"] = data.get("summary") or data.get("description") or "Performance overview"
        return data


# ---------------------------------------------------------------------------
# Top-level result — the Engineer Agent's output contract
# ---------------------------------------------------------------------------

class EngineerResult(BaseModel):
    """
    The full structured output of the CHAI Engineer Agent.

    Not every field will be populated for every problem. Sections that are
    irrelevant to the user's query should be left as ``None`` or empty.
    """

    # Metadata
    agent: str = Field(default="engineer", description="Agent identifier.")
    status: AgentStatus = Field(default=AgentStatus.COMPLETED, description="Execution status.")

    # Core analysis
    problem_understanding: str = Field(..., description="How the Engineer Agent interprets the problem.")

    # Requirements
    functional_requirements: List[str] = Field(default_factory=list, description="Functional technical requirements.")
    non_functional_requirements: List[str] = Field(default_factory=list, description="Non-functional requirements (performance, reliability, etc.).")

    # Architecture & components
    architecture: Optional[ArchitectureDesign] = Field(None, description="System architecture design.")
    components: List[str] = Field(default_factory=list, description="Major system components.")
    technology_recommendations: List[TechnologyRecommendation] = Field(default_factory=list, description="Recommended technologies with rationale.")

    # Data & APIs
    data_flow: List[DataFlowStep] = Field(default_factory=list, description="Data flow through the system.")
    api_design: List[APIEndpoint] = Field(default_factory=list, description="Recommended API endpoints.")
    database_design: Optional[DatabaseDesign] = Field(None, description="Database/storage design.")

    # AI/ML
    ai_ml_design: Optional[AIMLDesign] = Field(None, description="AI/ML architecture if relevant.")

    # Integration
    integrations: List[str] = Field(default_factory=list, description="External integration requirements.")

    # Quality attributes
    scalability: Optional[ScalabilityDesign] = Field(None, description="Scalability design.")
    performance: Optional[PerformanceDesign] = Field(None, description="Performance design.")

    # Plan & risks
    implementation_plan: List[ImplementationPhase] = Field(default_factory=list, description="Phased implementation plan.")
    technical_risks: List[TechnicalRisk] = Field(default_factory=list, description="Technical risks with mitigation.")

    # Constraints, tradeoffs, assumptions
    constraints: List[str] = Field(default_factory=list, description="Technical constraints identified.")
    tradeoffs: List[Tradeoff] = Field(default_factory=list, description="Engineering tradeoffs.")
    assumptions: List[str] = Field(default_factory=list, description="Assumptions made by the agent.")
    missing_information: List[str] = Field(default_factory=list, description="Information that would materially affect the architecture.")


# ---------------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------------
# The coordinator (backend/core/coordinator.py) imports EngineerOutput from
# backend.agents.engineer.models and accesses `technical_architecture` via
# model_dump(). We keep that alias working through models.py.

class EngineerOutput(BaseModel):
    """
    Backward-compatible output model that the Coordinator consumes.

    This is a flattened projection of ``EngineerResult`` so that the
    existing coordinator code (which accesses ``technical_architecture``)
    keeps working without modification.
    """

    # Fields the coordinator already accesses
    technical_architecture: str = Field(default="", description="Architecture overview text.")
    recommended_technologies: list[str] = Field(default_factory=list)
    components_and_apis: list[str] = Field(default_factory=list)
    data_flow: str = Field(default="", description="Data flow summary text.")
    implementation_plan: list[str] = Field(default_factory=list)

    # Full structured result embedded for downstream agents
    engineer_result: Optional[EngineerResult] = Field(None, description="Full structured Engineer analysis.")

    @classmethod
    def from_engineer_result(cls, result: EngineerResult) -> "EngineerOutput":
        """Project an ``EngineerResult`` into the backward-compatible shape."""
        arch_text = ""
        if result.architecture:
            arch_text = result.architecture.overview
            if result.architecture.pattern:
                arch_text += f" | Pattern: {result.architecture.pattern}"

        tech_list = [
            f"{t.technology}: {t.purpose}" for t in result.technology_recommendations
        ]

        components_apis: list[str] = list(result.components)
        for ep in result.api_design:
            components_apis.append(f"{ep.method} {ep.path} — {ep.purpose}")

        df_text = " → ".join(
            f"{s.source} → {s.destination}" for s in result.data_flow
        ) if result.data_flow else ""

        plan_list = [
            f"{p.phase}: {p.description}" for p in result.implementation_plan
        ]

        return cls(
            technical_architecture=arch_text,
            recommended_technologies=tech_list,
            components_and_apis=components_apis,
            data_flow=df_text,
            implementation_plan=plan_list,
            engineer_result=result,
        )
