"""
Routing and classification module for CHAI query coordination.
Determines whether incoming queries require full 6-agent coordination
or a streamlined single-pass response.
"""
import re
from typing import Optional, List, Literal
from backend.core.schemas import RouteDecision, RouteType, ComplexityType

ROUTE_SIMPLE: RouteType = "simple"
ROUTE_COMPLEX: RouteType = "complex"

COMPLEX_AGENTS: List[str] = [
    "researcher",
    "strategist",
    "engineer",
    "guardian",
    "security",
    "evaluator",
]

SIMPLE_AGENTS: List[str] = []

COMPLEX_KEYWORDS = {
    "design", "architect", "architecture", "platform", "system", "infrastructure",
    "healthcare", "security", "threat", "scalab", "multi-agent", "agentic",
    "tradeoff", "trade-off", "tradeoffs", "trade-offs", "policy", "pipeline",
    "strategy", "deployment", "compliance", "offline", "protocol", "framework",
    "database", "distributed", "microservice", "evaluate", "evaluation",
    "recommend", "compare", "versus", "vs", "resilient", "vulnerability",
}

SIMPLE_PATTERNS = [
    r"^what\s+is\s+a\s+[^?.]+[.?]?$",
    r"^what\s+is\s+an\s+[^?.]+[.?]?$",
    r"^what\s+is\s+[^?.]+[.?]?$",
    r"^what\s+are\s+[^?.]+[.?]?$",
    r"^what\s+is\s+\d+\s*[\+\-\*\/]\s*\d+[.?]?$",
    r"^define\s+[^?.]+[.?]?$",
    r"^definition\s+of\s+[^?.]+[.?]?$",
    r"^explain\s+what\s+[^?.]+[.?]?$",
    r"^what\s+does\s+[^?.]+mean[.?]?$",
    r"^how\s+do\s+i\s+print\s+[^?.]+[.?]?$",
    r"^who\s+invented\s+[^?.]+[.?]?$",
    r"^meaning\s+of\s+[^?.]+[.?]?$",
]


def route_request(problem: str, context: Optional[str] = None) -> RouteDecision:
    """
    Deterministically evaluates query complexity and selects the appropriate route.

    Returns:
        RouteDecision containing route ('simple' or 'complex'), complexity,
        reasoning, and required agents.
    """
    cleaned = (problem or "").strip()
    if not cleaned:
        return RouteDecision(
            route=ROUTE_SIMPLE,
            complexity="low",
            reasoning="Empty query provided; routed to simple default handler.",
            required_agents=SIMPLE_AGENTS,
        )

    lower = cleaned.lower()
    words = set(re.findall(r"\b\w+\b", lower))

    # 1. Complex keyword and multi-constraint signals
    matched_complex = [k for k in COMPLEX_KEYWORDS if k in lower or k in words]
    if matched_complex:
        return RouteDecision(
            route=ROUTE_COMPLEX,
            complexity="high",
            reasoning=f"Complex domain signals detected: {', '.join(sorted(matched_complex)[:3])}",
            required_agents=COMPLEX_AGENTS,
        )

    # 2. Check for explicit simple definition/factual query patterns
    for pat in SIMPLE_PATTERNS:
        if re.match(pat, lower):
            return RouteDecision(
                route=ROUTE_SIMPLE,
                complexity="low",
                reasoning="Direct factual definition query pattern detected.",
                required_agents=SIMPLE_AGENTS,
            )

    # 3. Short single question heuristic (< 45 chars ending with question mark)
    if len(lower) < 45 and lower.endswith("?") and not matched_complex:
        return RouteDecision(
            route=ROUTE_SIMPLE,
            complexity="low",
            reasoning="Short factual query without system architectural keywords.",
            required_agents=SIMPLE_AGENTS,
        )

    # 4. Default: Standard complex multi-agent reasoning
    return RouteDecision(
        route=ROUTE_COMPLEX,
        complexity="high",
        reasoning="Open-ended problem statement requiring multi-agent analysis.",
        required_agents=COMPLEX_AGENTS,
    )


class Router:
    """Static wrapper for query classification and route decisions."""

    @staticmethod
    def route(problem: str, context: Optional[str] = None) -> RouteDecision:
        return route_request(problem, context)

    @staticmethod
    def is_simple(problem: str) -> bool:
        return is_simple_query(problem)


def is_simple_query(problem: str) -> bool:
    """Backward compatibility helper for quick boolean simple route checks."""
    return route_request(problem).route == ROUTE_SIMPLE


__all__ = [
    "ROUTE_SIMPLE",
    "ROUTE_COMPLEX",
    "COMPLEX_AGENTS",
    "SIMPLE_AGENTS",
    "RouteDecision",
    "Router",
    "route_request",
    "is_simple_query",
]
