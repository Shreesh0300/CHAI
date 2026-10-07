"""
CHAI Synthesizer Agent package.

Exports the primary SynthesizerAgent and structured output models.
"""

from backend.agents.synthesizer.agent import SynthesizerAgent
from backend.agents.synthesizer.schemas import (
    AgentStatus,
    KeyDecision,
    SupportingFinding,
    ResolvedConflict,
    UnresolvedConflict,
    ProvenanceItem,
    SynthesizerResult,
    SynthesizerOutput,
)

__all__ = [
    "SynthesizerAgent",
    "AgentStatus",
    "KeyDecision",
    "SupportingFinding",
    "ResolvedConflict",
    "UnresolvedConflict",
    "ProvenanceItem",
    "SynthesizerResult",
    "SynthesizerOutput",
]
