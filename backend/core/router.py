"""
Routing and classification module for CHAI query coordination.
Determines whether incoming queries require full multi-agent coordination
or a streamlined single-pass direct LLM response.
"""
from __future__ import annotations

import re
from typing import Optional, List, Literal
from backend.core.schemas import RouteDecision, RouteType, ComplexityType
from backend.shared.logger import get_logger

logger = get_logger(__name__)

ROUTE_SIMPLE: RouteType = "simple"
ROUTE_COMPLEX: RouteType = "complex"

# Canonical specialist agent lists
COMPLEX_AGENTS: List[str] = [
    "researcher",
    "strategist",
    "engineer",
    "guardian",
    "security",
    "evaluator",
]

PERSONAL_CAREER_AGENTS: List[str] = [
    "researcher",
    "strategist",
    "guardian",
    "evaluator",
]

BUSINESS_STRATEGY_AGENTS: List[str] = [
    "researcher",
    "strategist",
    "guardian",
    "evaluator",
]

SIMPLE_AGENTS: List[str] = []

# Alias for backwards/future compatibility
RouterDecision = RouteDecision

# ---------------------------------------------------------------------------
# Specific detection regexes and keyword sets
# ---------------------------------------------------------------------------

_CAREER_PATTERNS = [
    r"\bparents\s+want\s+me\s+to\b",
    r"\bfinancially\s+dependent\b",
    r"\bfinancial\s+situation\b",
    r"\bshould\s+i\s+quit(\s+my)?\s+job\b",
    r"\bquit\s+my\s+job\b",
    r"\bchoose\s+(between\s+)?(ai|tech|engineering|coding)\s+or\s+(a\s+)?government\s+job\b",
    r"\bwhat\s+should\s+i\s+do\b.*\b(parents|career|job|dependent|financial)\b",
    r"\b(parents|family)\b.*\bwhat\s+should\s+i\s+do\b",
]

_ARCHITECTURE_PATTERNS = [
    r"\b(design|architect)\s+(a|an|our)\s+",
    r"\barchitecture\s+for\b",
    r"\b(system|technical)\s+architecture\b",
    r"\brag\s+system\b",
    r"\bmulti-agent\s+architecture\b",
    r"\bdistributed\s+consensus\b",
    r"\bscalable\s+healthcare\s+rag\b",
    r"\bsecure\s+multi-agent\b",
]

_MULTI_CONSTRAINT_COMPARISON_PATTERNS = [
    r"\bcompare\b.+\band\b.+\bfor\b.+(scalable|multi-tenant|saas|production|microservice)",
    r"\bcompare\b.+\band\b.+\bconsidering\b.+",
    r"\brange\s+of\s+trade-offs\b",
    r"\banalyze\s+the\s+risks\s+and\s+trade-offs\b",
    r"\bresearch-backed\s+comparison\b",
]

_BUSINESS_STRATEGY_PATTERNS = [
    r"\bbusiness\s+strategy\s+for\b",
    r"\blaunching\s+an?\s+ai\s+startup\b",
    r"\beconomic\s+risks\s+of\s+launching\b",
    r"\bgo-to-market\s+strategy\b",
]

_SIMPLE_EXACT_PATTERNS = [
    r"^what\s+is\s+a\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+is\s+an\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+is\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+are\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^define\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^definition\s+of\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^give\s+me\s+the\s+definition\s+of\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^explain\s+what\s+is\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^explain\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^who\s+invented\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^convert\s+\d+(\.\d+)?\s*[a-zA-Z]+\s+to\s+[a-zA-Z]+[.?]?$",
    r"^what\s+is\s+\d+\s*[\+\-\*\/]\s*\d+[.?]?$",
    r"^\d+\s*[\+\-\*\/]\s*\d+[.?]?$",
    r"^how\s+do\s+i\s+print\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+does\s+([a-zA-Z0-9_\- ]+)\s+mean[.?]?$",
    r"^is\s+python\s+better\s+than\s+java[.?]?$",
    r"^(hi|hii|hello|hey|greetings|howdy|good\s+(morning|afternoon|evening))[.!]?$",
]

# Modifiers inside a definition query that escalate it to complex
_COMPLEX_ESCALATION_KEYWORDS = {
    "architecture", "design", "scalable", "multi-tenant", "trade-off",
    "tradeoff", "trade-offs", "tradeoffs", "production", "multi-agent",
    "rag system", "resilient", "distributed consensus", "fault tolerance",
    "economic risk", "security threat", "vulnerability",
}


def _detect_domain(lower: str) -> str:
    """Detects query domain from semantic content."""
    if any(k in lower for k in ("parents", "job", "career", "quit", "dependent", "financial situation")):
        return "personal_career"
    if any(k in lower for k in ("startup", "business strategy", "economic risk", "go-to-market", "monetization")):
        return "business_strategy"
    if any(k in lower for k in ("healthcare", "clinical", "patient", "medical", "hipaa", "doctor")):
        return "healthcare"
    if any(k in lower for k in ("security", "threat", "vulnerability", "cve", "penetration", "auth", "encryption")):
        return "cybersecurity"
    if any(k in lower for k in (
        "tech stack", "technology stack", "architecture", "microservice", "database", "postgresql", "mongodb",
        "system", "software", "rag", "consensus", "distributed", "python", "java", "code"
    )):
        return "software_engineering"
    return "general"


def _detect_requested_depth(lower: str) -> Literal["brief", "normal", "deep"]:
    """Determines requested depth of reasoning based on semantic triggers and user phrasing."""
    # Deep reasoning keywords (multi-aspect, comprehensive analysis, explicit detail requests)
    if any(k in lower for k in (
        "detailed", "in-depth", "deep dive", "comprehensive", "research-backed",
        "thorough", "with examples", "edge cases", "deep analysis", "full explanation",
        "full details", "complete report", "compare in depth", "compare thoroughly",
        "in detail", "explain comprehensively", "research this",
    )):
        return "deep"

    # Brief / concise keywords (direct lookups, definitions, arithmetic, short answers)
    if any(k in lower for k in (
        "brief", "quick", "short", "in one sentence", "in one line", "short answer",
        "just tell me", "define", "definition", "full form of", "who invented", "who is",
    )):
        return "brief"

    # Direct short factual questions (< 50 chars starting with factual words)
    if (lower.startswith("what is ") or lower.startswith("what are ") or lower.startswith("who is ")) and len(lower) < 50:
        return "brief"

    return "normal"


def route_request(problem: str, context: Optional[str] = None) -> RouteDecision:
    """
    Evaluates query complexity and selects the appropriate route.

    The Router is the decision gate:
    - SIMPLE: direct LLM response without invoking multi-agent pipeline
    - COMPLEX: coordinated multi-agent deliberation with domain-relevant agents

    Complexity considers:
    - Reasoning depth, ambiguity, trade-offs, architecture/design
    - Consequential personal/career decisions
    - Safety, risks, and external research needs
    """
    cleaned = (problem or "").strip()
    if not cleaned:
        decision = RouteDecision(
            route=ROUTE_SIMPLE,
            complexity="low",
            reasoning="Empty query provided; routed to simple direct handler.",
            required_agents=SIMPLE_AGENTS,
            confidence=0.99,
            reasons=["empty query", "no reasoning required"],
            domain="general",
            requires_external_information=False,
            requires_multi_agent_reasoning=False,
            requested_depth="brief",
        )
        _log_decision(decision)
        return decision

    lower = cleaned.lower()
    full_text = f"{lower} {context.lower()}" if context else lower
    domain = _detect_domain(full_text)
    requested_depth = _detect_requested_depth(full_text)

    # =========================================================================
    # 1. Check for COMPLEX triggers
    # =========================================================================

    # 1A. Consequential personal / career decisions (dilemmas, trade-offs, risks)
    is_career_dilemma = any(re.search(pat, lower) for pat in _CAREER_PATTERNS)
    if is_career_dilemma:
        decision = RouteDecision(
            route=ROUTE_COMPLEX,
            complexity="high",
            reasoning="Consequential personal/career dilemma requiring trade-off deliberation and risk guidance.",
            required_agents=PERSONAL_CAREER_AGENTS,
            confidence=0.95,
            reasons=[
                "consequential personal/career decision",
                "trade-offs and financial dependency considerations",
                "requires strategic, ethical, and guardian risk evaluation",
                "software engineering and security agents excluded as irrelevant",
            ],
            domain="personal_career",
            requires_external_information=False,  # Context is user-specific; do NOT hit financial/external APIs
            requires_multi_agent_reasoning=True,
            requested_depth=requested_depth,
        )
        _log_decision(decision)
        return decision

    # 1B. System architecture and design
    is_architecture = any(re.search(pat, lower) for pat in _ARCHITECTURE_PATTERNS)
    if is_architecture:
        has_security = any(k in lower for k in ("security", "threat", "secure", "vulnerability", "auth"))
        reasons = [
            "system architecture design request",
            "multi-agent and component interaction requirements",
            "scalability and resilience analysis",
        ]
        if has_security:
            reasons.append("security and compliance requirements")

        decision = RouteDecision(
            route=ROUTE_COMPLEX,
            complexity="high",
            reasoning="System architecture and engineering design requiring multi-agent technical deliberation.",
            required_agents=COMPLEX_AGENTS,
            confidence=0.96,
            reasons=reasons,
            domain=domain if domain != "general" else "software_engineering",
            requires_external_information=True,
            requires_multi_agent_reasoning=True,
            requested_depth=requested_depth,
        )
        _log_decision(decision)
        return decision

    # 1C. Multi-constraint comparisons and trade-offs
    is_multi_comparison = any(re.search(pat, lower) for pat in _MULTI_CONSTRAINT_COMPARISON_PATTERNS)
    if is_multi_comparison:
        decision = RouteDecision(
            route=ROUTE_COMPLEX,
            complexity="high",
            reasoning="Multi-constraint technical comparison requiring architectural trade-off analysis.",
            required_agents=COMPLEX_AGENTS,
            confidence=0.94,
            reasons=[
                "multi-technology comparison across production criteria",
                "trade-off and scalability assessment",
                "independent multi-perspective evaluation needed",
            ],
            domain=domain if domain != "general" else "software_engineering",
            requires_external_information=True,
            requires_multi_agent_reasoning=True,
            requested_depth=requested_depth,
        )
        _log_decision(decision)
        return decision

    # 1D. Business strategy & economic risk analysis
    is_business_strategy = any(re.search(pat, lower) for pat in _BUSINESS_STRATEGY_PATTERNS)
    if is_business_strategy:
        decision = RouteDecision(
            route=ROUTE_COMPLEX,
            complexity="high",
            reasoning="Business strategy and economic risk analysis requiring coordinated strategic analysis.",
            required_agents=BUSINESS_STRATEGY_AGENTS,
            confidence=0.93,
            reasons=[
                "strategic business planning",
                "economic and operational risk assessment",
                "requires research and guardian validation",
            ],
            domain="business_strategy",
            requires_external_information=True,
            requires_multi_agent_reasoning=True,
            requested_depth="deep" if requested_depth == "deep" else "normal",
        )
        _log_decision(decision)
        return decision

    # 1E. Explicit research-backed or in-depth analysis requests
    if "research-backed" in lower or (requested_depth == "deep" and any(k in lower for k in ("risk", "analysis", "compare", "evaluation"))):
        decision = RouteDecision(
            route=ROUTE_COMPLEX,
            complexity="high",
            reasoning="Explicit request for research-backed analysis requiring coordinated multi-agent evidence.",
            required_agents=COMPLEX_AGENTS if domain in ("software_engineering", "cybersecurity") else BUSINESS_STRATEGY_AGENTS,
            confidence=0.92,
            reasons=[
                "explicit deep research-backed requirement",
                "multi-source evidence synthesis needed",
            ],
            domain=domain,
            requires_external_information=True,
            requires_multi_agent_reasoning=True,
            requested_depth="deep",
        )
        _log_decision(decision)
        return decision

    # 1F. Healthcare risk analysis
    if domain == "healthcare" and any(k in lower for k in ("risk", "trade-off", "tradeoff", "autonomous", "platform", "compliance")):
        decision = RouteDecision(
            route=ROUTE_COMPLEX,
            complexity="high",
            reasoning="Healthcare risk and trade-off analysis requiring multi-agent safety and guardian evaluation.",
            required_agents=COMPLEX_AGENTS,
            confidence=0.95,
            reasons=[
                "healthcare safety and ethical considerations",
                "clinical risk analysis and mitigation planning",
            ],
            domain="healthcare",
            requires_external_information=True,
            requires_multi_agent_reasoning=True,
            requested_depth=requested_depth,
        )
        _log_decision(decision)
        return decision

    # 1G. Cybersecurity threats and tradeoffs
    if domain == "cybersecurity" and any(k in lower for k in ("threat", "tradeoff", "trade-off", "cloud", "audit")):
        decision = RouteDecision(
            route=ROUTE_COMPLEX,
            complexity="high",
            reasoning="Security threat and trade-off assessment requiring multi-agent evaluation.",
            required_agents=COMPLEX_AGENTS,
            confidence=0.95,
            reasons=[
                "security threat modeling and attack surface analysis",
                "trade-off and safeguard evaluation",
            ],
            domain="cybersecurity",
            requires_external_information=True,
            requires_multi_agent_reasoning=True,
            requested_depth=requested_depth,
        )
        _log_decision(decision)
        return decision

    # =========================================================================
    # 2. Check for SIMPLE triggers
    # =========================================================================

    for pat in _SIMPLE_EXACT_PATTERNS:
        m = re.match(pat, lower)
        if m:
            # Check if inner concept contains complex escalation keywords
            concept_extracted = (m.group(1) or "") if (m.groups() and m.group(1) is not None) else ""
            concept_lower = concept_extracted.lower()
            escalated = any(esc in concept_lower for esc in _COMPLEX_ESCALATION_KEYWORDS)
            if not escalated:
                decision = RouteDecision(
                    route=ROUTE_SIMPLE,
                    complexity="low",
                    reasoning="Direct factual or conceptual definition query pattern detected.",
                    required_agents=SIMPLE_AGENTS,
                    confidence=0.98,
                    reasons=[
                        "single factual request or direct definition",
                        "no multi-agent coordination or architectural trade-offs required",
                    ],
                    domain=domain if domain != "personal_career" else "general",
                    requires_external_information=False,
                    requires_multi_agent_reasoning=False,
                    requested_depth="brief",
                )
                _log_decision(decision)
                return decision

    # 3. Short single question heuristic (< 50 chars, ends with ?, no complex signals)
    if len(lower) < 50 and lower.endswith("?") and not any(k in lower for k in ("should i", "design", "architect", "compare")):
        decision = RouteDecision(
            route=ROUTE_SIMPLE,
            complexity="low",
            reasoning="Short factual query without architectural or decision-making complexity.",
            required_agents=SIMPLE_AGENTS,
            confidence=0.95,
            reasons=["short single-question query", "no multi-agent coordination required"],
            domain=domain if domain != "personal_career" else "general",
            requires_external_information=False,
            requires_multi_agent_reasoning=False,
            requested_depth="brief",
        )
        _log_decision(decision)
        return decision

    # 4. Default fallback: Open-ended complex multi-agent reasoning
    decision = RouteDecision(
        route=ROUTE_COMPLEX,
        complexity="high",
        reasoning="Open-ended problem statement requiring coordinated multi-agent deliberation.",
        required_agents=COMPLEX_AGENTS,
        confidence=0.90,
        reasons=["open-ended problem statement", "multi-faceted coordination required"],
        domain=domain,
        requires_external_information=True,
        requires_multi_agent_reasoning=True,
        requested_depth=requested_depth,
    )
    _log_decision(decision)
    return decision


def _log_decision(decision: RouteDecision) -> None:
    """Emits structured observability log for router decision."""
    reason_summary = decision.reasons[0] if decision.reasons else decision.reasoning
    logger.info(
        f"ROUTER DECISION\n"
        f"    complexity = {decision.route}\n"
        f"    confidence = {decision.confidence:.2f}\n"
        f"    domain = {decision.domain}\n"
        f"    reason = \"{reason_summary}\""
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
    "PERSONAL_CAREER_AGENTS",
    "BUSINESS_STRATEGY_AGENTS",
    "SIMPLE_AGENTS",
    "RouteDecision",
    "RouterDecision",
    "Router",
    "route_request",
    "is_simple_query",
]
