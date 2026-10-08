"""
Backward-compatible models for the Engineer Agent.

The Coordinator (``backend/core/coordinator.py``) imports ``EngineerOutput``
from this module.  We re-export the canonical definition from ``schemas.py``
so the import path remains stable.
"""

from backend.agents.engineer.schemas import EngineerOutput, EngineerResult  # noqa: F401

__all__ = ["EngineerOutput", "EngineerResult"]
