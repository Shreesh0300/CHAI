"""
Tools and interfaces for the Strategist Agent.
Minimal interfaces for strategic prioritization and roadmap helpers without
introducing external planning dependencies, web scrapers, or vector databases.
"""
from typing import List, Dict, Any, Optional
from backend.shared.logger import get_logger

logger = get_logger(__name__)


def estimate_strategic_complexity(tasks: List[str]) -> Dict[str, Any]:
    """
    Minimal helper interface for evaluating sequence complexity.
    """
    return {
        "task_count": len(tasks),
        "status": "ready"
    }
