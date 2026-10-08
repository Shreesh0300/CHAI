"""
Routing logic for CHAI Multi-Agent Architecture.

Determines the execution path and agent selection based on problem complexity
and user specifications.
"""
from typing import List, Optional

CANONICAL_AGENTS = [
    "researcher",
    "strategist",
    "engineer",
    "guardian",
    "security",
    "evaluator",
]

SIMPLE_QUERY_PREFIXES = (
    "what is a python list",
    "what is a list in python",
    "what is a variable",
    "define a ",
    "what is the definition of",
)


def is_simple_factual_query(problem: str) -> bool:
    """
    Identifies trivial or simple definitional questions where running full
    system engineering and threat modelling is unnecessary.
    """
    cleaned = problem.strip().lower()
    if not cleaned:
        return False
    
    # Check explicit simple definitional queries
    for prefix in SIMPLE_QUERY_PREFIXES:
        if cleaned.startswith(prefix):
            return True
            
    # Very short single-fact definitions without design/architecture keywords
    words = cleaned.split()
    if len(words) <= 6 and (cleaned.startswith("what is") or cleaned.startswith("define")):
        technical_design_keywords = {
            "design", "system", "architecture", "platform", "infrastructure",
            "security", "patient", "clinical", "hospital", "financial", "bank", "deploy"
        }
        if not any(kw in words for kw in technical_design_keywords):
            return True
            
    return False


def route_agents_for_problem(
    problem: str,
    requested_agents: Optional[List[str]] = None,
    allow_conditional_routing: bool = False,
) -> List[str]:
    """
    Routes and selects which agents should run for a given problem.

    Parameters
    ----------
    problem : str
        The input query.
    requested_agents : Optional[List[str]]
        Explicit agent list if specified by the user or client.
    allow_conditional_routing : bool
        If True, permits scaling down to fewer agents for simple questions.

    Returns
    -------
    List[str]
        Ordered list of agent identifiers to execute.
    """
    if requested_agents:
        # Filter to valid canonical agents preserving requested order
        valid = [a.lower().strip() for a in requested_agents if a.lower().strip() in CANONICAL_AGENTS]
        if valid:
            return valid

    if allow_conditional_routing and is_simple_factual_query(problem):
        # Lightweight route for trivial definitional queries
        return ["researcher", "evaluator"]

    # Default: Full comprehensive 6-agent collaborative pipeline
    return list(CANONICAL_AGENTS)
