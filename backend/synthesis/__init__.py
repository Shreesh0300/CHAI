"""
CHAI Synthesis package.
Exports Synthesizer, SynthesisResult, and FinalResult.
"""
from backend.synthesis.synthesizer import Synthesizer
from backend.core.contracts import SynthesisResult, FinalResult
from backend.synthesis.response_formatter import format_user_facing_response
from backend.synthesis.response_planner import (
    ResponsePlan,
    plan_response,
    detect_domains,
    detect_intent,
    extract_explicit_requirements,
)

__all__ = [
    "Synthesizer",
    "SynthesisResult",
    "FinalResult",
    "format_user_facing_response",
    "ResponsePlan",
    "plan_response",
    "detect_domains",
    "detect_intent",
    "extract_explicit_requirements",
]
