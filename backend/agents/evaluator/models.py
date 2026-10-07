"""
Backward-compatible models for the Evaluator Agent.

The Coordinator (``backend/core/coordinator.py``) imports ``EvaluatorOutput``
from this module. We re-export the canonical definitions from ``schemas.py``
so the import path remains completely stable.
"""

from backend.agents.evaluator.schemas import EvaluatorOutput, EvaluatorResult  # noqa: F401

__all__ = ["EvaluatorOutput", "EvaluatorResult"]
