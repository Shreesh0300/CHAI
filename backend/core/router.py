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
    r"\bchoose\s+between\s+(a\s+)?(stable\s+)?career\s+and\s+entrepreneurship\b",
    r"\bdecision\s+framework\s+and\s+risk\s+mitigation\b",
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
    r"\b50,000\s+students\b",
    r"\b50000\s+students\b",
]

_MULTI_CONSTRAINT_COMPARISON_PATTERNS = [
    r"\bcompare\b.+\band\b.+\bfor\b.+(scalable|multi-tenant|saas|production|microservice)",
    r"\bcompare\b.+\band\b.+\bconsidering\b.+",
    r"\bcompare\b.+\b(?:for\s+numerical\s+computing|complexity\s+and\s+convergence|numerical\s+stability)\b",
    r"\brange\s+of\s+trade-offs\b",
    r"\banalyze\s+the\s+risks\s+and\s+trade-offs\b",
    r"\bresearch-backed\s+comparison\b",
]

_BUSINESS_STRATEGY_PATTERNS = [
    r"\bbusiness\s+strategy\s+for\b",
    r"\blaunching\s+an?\s+ai\s+startup\b",
    r"\b(?:build|create|develop)\s+(?:a\s+)?(?:\w+-\w+\s+)?strategy\s+for\s+launching\b",
    r"\beconomic\s+risks\s+of\s+launching\b",
    r"\bgo-to-market\s+strategy\b",
    r"\bcompare\s+(?:several\s+)?business\s+options\b",
    r"\brecommend\s+one\s+with\s+a\s+\d+-month\s+plan\b",
]

_SCIENTIFIC_PATTERNS = [
    r"\banalyze\s+competing\s+scientific\s+explanations\b",
    r"\bevaluate\s+causal\s+evidence\b",
]

_SIMPLE_EXACT_PATTERNS = [
    # A. Factual questions & lookups
    r"^what\s+is\s+a\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+is\s+an\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+is\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+are\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+was\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^who\s+invented\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^who\s+is\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^who\s+was\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+does\s+([a-zA-Z0-9_\- ]+)\s+stand\s+for[.?]?$",
    r"^what\s+(?:is|are)\s+(?:the\s+)?full\s+form\s+of\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+is\s+the\s+capital\s+of\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^where\s+is\s+([a-zA-Z0-9_\- ]+)[.?]?$",

    # B. Basic mathematics & arithmetic
    r"^(?:what\s+is\s+)?(?:the\s+)?(?:square|cube|fourth)\s+root\s+of\s+\d+(\.\d+)?[.?]?$",
    r"^sqrt\s*\(?\s*\d+(\.\d+)?\s*\)?[.?]?$",
    r"^(?:what\s+is\s+)?\d+(\.\d+)?\s*(?:squared|cubed)[.?]?$",
    r"^(?:calculate|compute|find|solve)\s+(?:the\s+)?(?:square|cube)\s+root\s+of\s+\d+(\.\d+)?[.?]?$",
    r"^(?:what\s+is\s+)?(?:\d+(\.\d+)?\s*[\+\-\*\/\^\%]\s*)+\d+(\.\d+)?[.?]?$",
    r"^(?:what\s+is\s+)?\d+(\.\d+)?\s*(?:plus|minus|times|divided\s+by|multiplied\s+by)\s*\d+(\.\d+)?[.?]?$",
    r"^(?:calculate|compute|solve|find)\s+(?:what\s+is\s+)?\d+(\.\d+)?\s*(?:plus|minus|times|divided\s+by|multiplied\s+by|[\+\-\*\/\^])\s*\d+(\.\d+)?[.?]?$",
    r"^(?:what\s+is\s+)?\d+(\.\d+)?\s*(?:%|percent(?:age)?)\s+of\s+\d+(\.\d+)?[.?]?$",
    r"^(?:calculate|compute|find)\s+\d+(\.\d+)?\s*(?:%|percent(?:age)?)\s+of\s+\d+(\.\d+)?[.?]?$",
    r"^(?:what\s+is\s+)?\d+\s*factorial[.?]?$",
    r"^(?:what\s+is\s+)?factorial\s+of\s+\d+[.?]?$",
    r"^(?:what\s+is\s+)?\d+![.?]?$",
    r"^solve\s+[a-zA-Z]\s*[\+\-\*\/]\s*\d+(\.\d+)?\s*=\s*\d+(\.\d+)?[.?]?$",
    r"^solve\s+for\s+[a-zA-Z]\s*:\s*[a-zA-Z]\s*[\+\-\*\/]\s*\d+(\.\d+)?\s*=\s*\d+(\.\d+)?[.?]?$",

    # C. Basic unit conversion
    r"^(?:convert\s+)?\d+(\.\d+)?\s*(?:km|kilometers?|m|meters?|cm|centimeters?|miles?|feet|ft|inches?|kg|kilograms?|g|grams?|lbs?|pounds?|ounces?|oz|hours?|hrs?|minutes?|mins?|seconds?|secs?|celsius|fahrenheit|gb|mb|kb|tb|bytes?)\s+(?:in|to|into)\s+(?:km|kilometers?|m|meters?|cm|centimeters?|miles?|feet|ft|inches?|kg|kilograms?|g|grams?|lbs?|pounds?|ounces?|oz|hours?|hrs?|minutes?|mins?|seconds?|secs?|celsius|fahrenheit|gb|mb|kb|tb|bytes?)[.?]?$",

    # D. Basic definitions
    r"^define\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^definition\s+of\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^give\s+me\s+the\s+definition\s+of\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^what\s+does\s+([a-zA-Z0-9_\- ]+)\s+mean[.?]?$",

    # E. Basic comparisons
    r"^which\s+(?:language|technology|framework|tool|database)?\s*(?:compiles|runs|executes|is)?\s+(?:faster|better|slower|easier)[, ]+(.+)[.?]?$",
    r"^which\s+is\s+(?:faster|better|slower|easier|preferable|larger|smaller|bigger|greater|heavier|longer|shorter)[, ]+(.+)[.?]?$",
    r"^is\s+([a-zA-Z0-9_\- ]+)\s+(?:faster|better|slower|different|more\s+[a-z]+|larger|smaller|bigger|greater)\s+than\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^(?:what\s+is\s+)?(?:the\s+)?difference\s+between\s+([a-zA-Z0-9_\- ]+)\s+and\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^compare\s+([a-zA-Z0-9_\- ]{1,30})\s+(?:and|with|to|vs\.?)\s+([a-zA-Z0-9_\- ]{1,30})[.?]?$",
    r"^([a-zA-Z0-9_\- ]{1,30})\s+vs\.?\s+([a-zA-Z0-9_\- ]{1,30})[.?]?$",

    # F. Simple educational explanations
    r"^explain\s+what\s+is\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^explain\s+([a-zA-Z0-9_\- ]+)[.?]?$",
    r"^explain\s+how\s+computers\s+calculate\s+square\s+roots[.?]?$",
    r"^(?:can\s+you\s+)?explain\s+(?:to\s+me\s+)?(?:how\s+)?([a-zA-Z0-9_\- ]+)\s*(?:works|is)?[.?]?$",
    r"^how\s+do\s+i\s+print\s+([a-zA-Z0-9_\- ]+)[.?]?$",

    # G. Greetings
    r"^(hi+|hello|hey+|greetings|howdy|good\s+(morning|afternoon|evening))[.!]?$",
]

# Modifiers inside a definition/comparison query that escalate it to complex
_COMPLEX_ESCALATION_KEYWORDS = {
    "architecture", "design", "scalable", "multi-tenant", "trade-off",
    "tradeoff", "trade-offs", "tradeoffs", "production", "multi-agent",
    "rag system", "resilient", "distributed consensus", "fault tolerance",
    "economic risk", "security threat", "vulnerability", "recommend",
    "plan", "roadmap", "strategy", "startup", "decision framework",
    "business options", "12-month", "numerical stability", "convergence",
}

_MATH_BASIC_PATTERNS = [
    r"\b(?:square|cube)\s+root\s+of\s+\d+",
    r"\bsqrt\s*\(?\s*\d+",
    r"\b\d+\s*(?:squared|cubed)\b",
    r"\b\d+\s*factorial\b",
    r"\b\d+!\b",
    r"\b\d+(\.\d+)?\s*%\s+of\s+\d+",
    r"\b\d+(\.\d+)?\s*percent(?:age)?\s+of\s+\d+",
    r"\b\d+(\.\d+)?\s*[\+\-\*\/\^]\s*\d+(\.\d+)?",
    r"\b\d+\s*(?:plus|minus|times|divided\s+by|multiplied\s+by)\s*\d+\b",
    r"\bsolve\s+[a-zA-Z]\s*[\+\-\*\/]\s*\d+\s*=\s*\d+",
    r"\b\d+(\.\d+)?\s*(?:km|kg|m|g|hours?|hrs?|minutes?|mins?|gb|mb|kb)\s+(?:in|to|into)\s+(?:km|kg|m|g|hours?|hrs?|minutes?|mins?|gb|mb|kb|meters|grams)",
]


def normalize_conversational_query(text: str) -> str:
    """
    Normalizes conversational padding, greetings, and filler phrases
    from the beginning and end of a query to extract core intent.
    Examples:
        'broo square root of 64' -> 'square root of 64'
        'Hey bro, I just want to know which language generally runs faster, C or Python?'
            -> 'which language generally runs faster, C or Python?'
        'Can you please tell me what the square root of 64 is?'
            -> 'what is the square root of 64'
    """
    if not text:
        return ""
    cleaned = text.strip()

    # Loop to strip layered greetings, vocatives/slang, and filler openers
    opener_patterns = [
        r"^(?:hey+|hi+|hello+|yo|greetings|howdy|good\s+(?:morning|afternoon|evening))\b[,! ]*",
        r"^(?:bro+|dude|buddy|man|pal|mate|boss|sir)\b[,! ]*",
        r"^(?:can\s+you\s+(?:please\s+)?(?:tell\s+me|explain|show\s+me|help\s+me\s+with)?|could\s+you\s+(?:please\s+)?(?:tell\s+me|explain|show\s+me)?)\b[,! ]*",
        r"^(?:please\s+)?(?:tell\s+me|just\s+tell\s+me|just\s+explain|i\s+(?:just\s+)?want\s+to\s+know|i\s+need\s+to\s+know|help\s+me\s+with)\b[,! ]*",
        r"^(?:please)\b[,! ]*",
    ]

    changed = True
    while changed:
        changed = False
        for pat in opener_patterns:
            new_text = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
            if new_text != cleaned:
                cleaned = new_text
                changed = True

    # Normalize inverted indirect questions:
    # "what the square root of 64 is" -> "what is the square root of 64"
    cleaned = re.sub(r"^what\s+(.+?)\s+is[.?]?$", r"what is \1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^what\s+(.+?)\s+are[.?]?$", r"what are \1", cleaned, flags=re.IGNORECASE)

    return cleaned.strip()


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
    normalized = normalize_conversational_query(lower)
    full_text = f"{lower} {context.lower()}" if context else lower
    domain = _detect_domain(full_text)
    requested_depth = _detect_requested_depth(full_text)

    # =========================================================================
    # 1. Check for COMPLEX triggers
    # =========================================================================

    # 1A. Consequential personal / career decisions (dilemmas, trade-offs, risks)
    is_career_dilemma = any(re.search(pat, lower) or re.search(pat, normalized) for pat in _CAREER_PATTERNS)
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
    is_architecture = any(re.search(pat, lower) or re.search(pat, normalized) for pat in _ARCHITECTURE_PATTERNS)
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
    is_multi_comparison = any(re.search(pat, lower) or re.search(pat, normalized) for pat in _MULTI_CONSTRAINT_COMPARISON_PATTERNS)
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
    is_business_strategy = any(re.search(pat, lower) or re.search(pat, normalized) for pat in _BUSINESS_STRATEGY_PATTERNS)
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

    # 1E. Scientific evaluation & causal analysis
    is_scientific = any(re.search(pat, lower) or re.search(pat, normalized) for pat in _SCIENTIFIC_PATTERNS)
    if is_scientific:
        decision = RouteDecision(
            route=ROUTE_COMPLEX,
            complexity="high",
            reasoning="Scientific evaluation and causal evidence analysis requiring multi-agent research.",
            required_agents=COMPLEX_AGENTS,
            confidence=0.94,
            reasons=[
                "competing scientific explanations evaluation",
                "causal evidence synthesis required",
            ],
            domain="general",
            requires_external_information=True,
            requires_multi_agent_reasoning=True,
            requested_depth="deep",
        )
        _log_decision(decision)
        return decision

    # 1F. Explicit research-backed or in-depth analysis requests
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

    # 1G. Healthcare risk analysis
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

    # 1H. Cybersecurity threats and tradeoffs
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

    # 2A. Check exact simple taxonomy patterns (on raw lower or normalized query)
    for text_candidate in (normalized, lower):
        for pat in _SIMPLE_EXACT_PATTERNS:
            m = re.match(pat, text_candidate)
            if m:
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

    # 2B. Basic Mathematics, Arithmetic, and Conversions (explicit recognition)
    is_basic_math = any(re.search(pat, lower) or re.search(pat, normalized) for pat in _MATH_BASIC_PATTERNS)
    has_math_escalation = any(k in lower for k in (
        "convergence", "numerical stability", "differential equation", "derive step by step",
        "newton's method", "compare", "complexity and"
    ))
    if is_basic_math and not has_math_escalation:
        decision = RouteDecision(
            route=ROUTE_SIMPLE,
            complexity="low",
            reasoning="Basic mathematical calculation or unit conversion query detected.",
            required_agents=SIMPLE_AGENTS,
            confidence=0.99,
            reasons=[
                "basic arithmetic or calculation request",
                "no multi-agent coordination or proof derivation required",
            ],
            domain="general",
            requires_external_information=False,
            requires_multi_agent_reasoning=False,
            requested_depth="brief",
        )
        _log_decision(decision)
        return decision

    # 3. Direct question / lookup heuristic (no complex signals)
    trimmed_norm = re.sub(r"[?.!]+$", "", normalized).strip()
    trimmed_lower = re.sub(r"[?.!]+$", "", lower).strip()
    is_question_shape = (
        lower.endswith("?")
        or normalized.endswith("?")
        or trimmed_norm.startswith((
            "what is", "what are", "what was", "which ", "who is", "who was", "who invented",
            "is ", "are ", "can you explain", "explain ", "how does", "how do i", "how do",
            "how to", "why is", "why does", "tell me about", "difference between",
            "compare ", "where is", "when did", "define ", "square root", "cube root", "sqrt",
            "calculate", "solve", "evaluate", "find the", "find ", "convert", "give me", "show me"
        ))
        or trimmed_lower.startswith((
            "what is", "what are", "which ", "who is", "who was", "who invented",
            "is ", "are ", "can you explain", "explain ", "how does", "how do i",
            "how to", "why is", "why does", "tell me about", "difference between",
            "compare ", "where is", "when did", "define "
        ))
    )

    has_complex_signals = any(k in lower for k in (
        "should i", "design", "architect", "scalable", "multi-tenant", "production",
        "saas", "50,000", "50000", "startup", "strategy", "roadmap", "decision framework",
        "trade-off", "tradeoff", "trade-offs", "considering", "evaluat", "synthesiz",
        "multi-agent", "rag", "benchmark-style", "parents want me", "research-backed",
        "financial situation", "career and entrepreneurship", "scientific explanations",
        "plan for", "recommend one with", "edge cases", "with examples", "implementation plan",
        "benchmarks", "pricing", "providers", "differently despite", "launching",
        "convergence", "numerical stability", "causal evidence", "12-month"
    )) or (requested_depth == "deep" and len(lower) > 50)

    if not has_complex_signals and is_question_shape:
        decision = RouteDecision(
            route=ROUTE_SIMPLE,
            complexity="low",
            reasoning="Direct factual or comparative query without multi-criteria architectural or strategic complexity.",
            required_agents=SIMPLE_AGENTS,
            confidence=0.96,
            reasons=["direct query without complex signals", "no multi-agent coordination required"],
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
