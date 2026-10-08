"""
Backward-compatible models for the Guardian Agent.

The Coordinator (``backend/core/coordinator.py``) imports ``GuardianOutput``
from this module. We re-export the canonical definitions from ``schemas.py``
so the import path remains completely stable.
"""

from backend.agents.guardian.schemas import GuardianOutput, GuardianResult  # noqa: F401

__all__ = ["GuardianOutput", "GuardianResult"]
