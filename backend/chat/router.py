"""
Lightweight Intent Router for CHAI.
Classifies incoming user messages into:
- CHAT: LangChain conversational pipeline (fast, personalized, concise, single-model)
- SOLVE: LangGraph multi-agent pipeline (deep 12-stage reasoning across specialists)
"""
import re
import json
import asyncio
from typing import Optional

from backend.chat.schemas import IntentResult
from backend.shared.llm_client import llm_client
from backend.shared.logger import get_logger

logger = get_logger(__name__)

# Heuristic patterns for unambiguous CHAT requests
GREETING_PATTERNS = [
    re.compile(r"^(?:hi|hey|hello|sup|yo|howdy|good\s+(?:morning|afternoon|evening|day))\b", re.IGNORECASE),
    re.compile(r"^(?:how\s+are\s+you|how's\s+it\s+going|what'?s\s+up|how\s+do\s+you\s+do)\b", re.IGNORECASE),
    re.compile(r"^(?:thanks|thank\s+you|appreciate\s+it|nice|cool|awesome|great)\b", re.IGNORECASE),
]

SIMPLE_CHAT_PATTERNS = [
    # Explanations of concepts
    re.compile(r"^(?:can\s+you\s+)?(?:explain|describe|define|summarize)\s+(?:what\s+is\s+|how\s+does\s+)?([a-zA-Z0-9_\s]{2,40})(?:\s+in\s+simple\s+terms)?\??$", re.IGNORECASE),
    re.compile(r"^(?:what\s+is|what\s+are|how\s+does|how\s+do)\s+([a-zA-Z0-9_\s]{2,40})\??$", re.IGNORECASE),
    # Day planning & light personal questions
    re.compile(r"^(?:help\s+me\s+plan\s+my\s+day|what\s+should\s+i\s+focus\s+on\s+today|plan\s+my\s+schedule)\b", re.IGNORECASE),
    # Conversational sharing
    re.compile(r"^(?:i(?:'ve|\s+have)\s+been\s+working\s+on\s+my\s+project|i(?:'m|\s+am)\s+tired|i\s+just\s+woke\s+up)\b", re.IGNORECASE),
    # Memory recall questions
    re.compile(r"^(?:remember\s+what\s+i\s+told\s+you|what\s+did\s+i\s+say|what\s+do\s+you\s+remember)\b", re.IGNORECASE),
    # Quick error lookup
    re.compile(r"^(?:what\s+does\s+this\s+error\s+mean|how\s+to\s+fix\s+this\s+syntax\s+error|explain\s+this\s+error)\b", re.IGNORECASE),
]

# Heuristic patterns for unambiguous SOLVE requests
COMPLEX_SOLVE_PATTERNS = [
    # Multi-variable life/career trade-off decisions
    re.compile(r"(?:choose\s+a\s+government\s+job\s+or\s+start\s+a\s+business)", re.IGNORECASE),
    re.compile(r"(?:accept\s+this\s+internship\s+or\s+focus\s+on\s+my\s+startup)", re.IGNORECASE),
    re.compile(r"(?:stable\s+job\s+or\s+(?:spend\s+\w+\s+years\s+)?building\s+a\s+startup)", re.IGNORECASE),
    re.compile(r"(?:compare\s+(?:the\s+)?financial\s+risk|opportunity\s+cost|downside\s+protection)", re.IGNORECASE),
    # System design & enterprise engineering
    re.compile(r"(?:design\s+.*\b(?:platform|architecture|system|infrastructure)\s+for\s+[\d,]+)", re.IGNORECASE),
    re.compile(r"(?:design\s+(?:a\s+)?(?:secure|scalable|production-ready|enterprise|distributed)[\w\s]{0,40}?(?:platform|architecture|system|infrastructure))", re.IGNORECASE),
    re.compile(r"(?:architect\s+(?:an?\s+)?(?:enterprise|distributed|scalable|cloud|microservice))", re.IGNORECASE),
    # Multi-strategy analysis & multi-year planning
    re.compile(r"(?:compare\s+these\s+(?:three|3|\w+)\s+(?:business\s+)?strategies\s+and\s+recommend)", re.IGNORECASE),
    re.compile(r"(?:analyze\s+(?:the\s+)?risks?\s+and\s+create\s+a\s+(?:\d+-year|two-year)\s+plan)", re.IGNORECASE),
    re.compile(r"(?:research\s+(?:the\s+)?competing\s+explanations\s+and\s+evaluate\s+(?:the\s+)?evidence)", re.IGNORECASE),
    # Explicit trade-off frameworks
    re.compile(r"(?:give\s+me\s+a\s+practical\s+two-year\s+plan|detailed\s+implementation\s+plan\s+with\s+trade-offs)", re.IGNORECASE),
]

ROUTER_PROMPT = """You are the CHAI Intent Router.
CHAI has two processing modes:
1. CHAT: Fast conversational response. Used for greetings, simple questions, concise explanations, casual conversation, daily tips, and basic code questions.
2. SOLVE: Full 12-stage multi-agent reasoning pipeline. Used for complex decisions, architectural system designs, multi-perspective trade-off evaluations, strategic multi-year plans, security evaluations, and deep comparative research.

Analyze the user's message and determine whether it should be routed to 'chat' or 'solve'.
If the query is a simple explanation or casual question, choose 'chat'.
If the query requires deep multi-agent coordination, risk analysis, or multi-faceted engineering design, choose 'solve'.

Output JSON:
{
  "intent": "chat" | "solve",
  "confidence": float between 0.0 and 1.0,
  "reason": "short explanation"
}
"""


class IntentRouter:
    """
    Determines whether a user query requires casual conversational chat
    or deep multi-agent solve orchestration.
    """

    async def classify(self, message: str) -> IntentResult:
        """
        Classifies message into CHAT or SOLVE with confidence and reasoning.
        """
        cleaned = (message or "").strip()
        if not cleaned:
            return IntentResult(intent="chat", confidence=1.0, reason="Empty message defaults to chat.")

        # 1. Deterministic SOLVE checks (high complexity queries)
        for pattern in COMPLEX_SOLVE_PATTERNS:
            if pattern.search(cleaned):
                reason = "Complex multi-variable trade-off, architectural design, or strategic risk planning requires 12-stage multi-agent reasoning."
                logger.info(f"[INTENT ROUTER] Intent: SOLVE (Heuristic match: {reason})")
                return IntentResult(intent="solve", confidence=0.98, reason=reason)

        # Multi-factor complexity heuristics:
        # Long prompt with multiple criteria, trade-offs, and design words
        words = cleaned.split()
        word_count = len(words)
        has_architecture = bool(re.search(r"\b(scalable|platform|enterprise|microservices|distributed|throughput|latency|infrastructure)\b", cleaned, re.IGNORECASE))
        has_comparison = bool(re.search(r"\b(compare|trade-offs?|pros and cons|versus|risk analysis|opportunity cost)\b", cleaned, re.IGNORECASE))
        has_decision = bool(re.search(r"\b(should i choose|which option|recommend between|evaluate between)\b", cleaned, re.IGNORECASE))
        has_multi_year = bool(re.search(r"\b(plan for \d+|two-year|5-year|roadmap|strategic plan)\b", cleaned, re.IGNORECASE))

        # If it has 2+ strong complexity indicators and significant length
        complexity_signals = sum([has_architecture, has_comparison, has_decision, has_multi_year])
        if complexity_signals >= 2 and word_count >= 15:
            reason = "Multiple interacting constraints and trade-off evaluation require coordinated multi-agent solve pipeline."
            logger.info(f"[INTENT ROUTER] Intent: SOLVE (Complexity signals: {complexity_signals})")
            return IntentResult(intent="solve", confidence=0.92, reason=reason)

        # 2. Deterministic CHAT checks (greetings & simple questions)
        for pattern in GREETING_PATTERNS:
            if pattern.search(cleaned):
                reason = "Conversational greeting or social exchange."
                logger.info(f"[INTENT ROUTER] Intent: CHAT ({reason})")
                return IntentResult(intent="chat", confidence=0.99, reason=reason)

        for pattern in SIMPLE_CHAT_PATTERNS:
            if pattern.search(cleaned):
                reason = "Direct explanation, conversational inquiry, or daily planning query handled directly by chat."
                logger.info(f"[INTENT ROUTER] Intent: CHAT ({reason})")
                return IntentResult(intent="chat", confidence=0.95, reason=reason)

        # Short questions (< 12 words) without complex engineering keywords default to CHAT
        if word_count < 12 and not has_architecture and not (has_comparison and has_decision):
            reason = "Concise question without multi-agent requirements handled directly by conversational model."
            logger.info(f"[INTENT ROUTER] Intent: CHAT (Short query: {word_count} words)")
            return IntentResult(intent="chat", confidence=0.88, reason=reason)

        # 3. LLM Fallback for ambiguous boundary queries
        try:
            prompt = f"{ROUTER_PROMPT}\n\nUser Message: \"{cleaned}\""
            raw_response = await asyncio.wait_for(
                llm_client.generate_content(
                    prompt=prompt,
                    temperature=0.0,
                    timeout=3.5,
                ),
                timeout=3.5,
            )
            if raw_response and not raw_response.startswith("Mock response"):
                # Clean code fence if present
                clean_json = raw_response.strip()
                if clean_json.startswith("```"):
                    clean_json = re.sub(r"^```(?:json)?\n?", "", clean_json)
                    clean_json = re.sub(r"\n?```$", "", clean_json)
                data = json.loads(clean_json)
                intent_val = data.get("intent", "chat").lower()
                if intent_val not in ("chat", "solve"):
                    intent_val = "chat"
                conf = float(data.get("confidence", 0.85))
                reason = data.get("reason", "Model classified query complexity.")
                logger.info(f"[INTENT ROUTER] Intent: {intent_val.upper()} (LLM classified, confidence={conf})")
                return IntentResult(intent=intent_val, confidence=conf, reason=reason)
        except Exception as exc:
            logger.debug(f"[INTENT ROUTER] LLM router fallback skipped: {exc}")

        # Default fallback: favor CHAT for simple safety, avoiding running 12 agents unnecessarily
        reason = "Default conversational path for standard query."
        logger.info(f"[INTENT ROUTER] Intent: CHAT (Default fallback)")
        return IntentResult(intent="chat", confidence=0.80, reason=reason)


# Global singleton instance
intent_router = IntentRouter()
