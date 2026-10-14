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
from backend.core.router import route_request, ROUTE_SIMPLE, ROUTE_COMPLEX
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
    # Conversational follow-ups, names, and personal reference questions
    re.compile(r"^(?:what\s+(?:am\s+i|is\s+[\w\s]{1,30}|are\s+we)\s+(?:building|working\s+on|doing|creating|making))\b", re.IGNORECASE),
    re.compile(r"^(?:what\s+[\w\s]{1,30}\s+is\s+(?:building|working\s+on|doing|creating|making))\b", re.IGNORECASE),
    re.compile(r"^(?:who\s+is\s+[\w\s]{1,30})\??$", re.IGNORECASE),
    re.compile(r"^(?:what\s+is\s+(?:my|the|our)\s+(?:project|startup|product|company)(?:'?s)?(?:\s+name)?)\??$", re.IGNORECASE),
    re.compile(r"^(?:what\s+is\s+(?:it|that|this)|tell\s+me\s+more\s+about\s+(?:it|that|this|him|her))\b", re.IGNORECASE),
    re.compile(r"^(?:what\s+did\s+(?:i|we|you)\s+(?:say|tell|mention|discuss))\b", re.IGNORECASE),
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
    re.compile(r"(?:design\s+(?:a\s+)?(?:comprehensive|secure|scalable|production-ready|enterprise|distributed|zero-trust)[\w\s\-]{0,50}?(?:platform|architecture|system|infrastructure))", re.IGNORECASE),
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
    Adapter between conversational chat API and authoritative CHAI core router (backend.core.router).
    Determines whether a user query requires casual conversational chat
    or deep multi-agent solve orchestration.
    """

    async def _classify_with_llm(self, cleaned: str) -> Optional[IntentResult]:
        """
        Attempts LLM-based classification for boundary queries.
        """
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
            clean_json = raw_response.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r"^```(?:json)?\n?", "", clean_json)
                clean_json = re.sub(r"\n?```$", "", clean_json)
            data = json.loads(clean_json)
            intent_val = data.get("intent", "").lower()
            if intent_val not in ("chat", "solve"):
                intent_val = "chat"
            conf = float(data.get("confidence", 0.85))
            reason = data.get("reason", "Model classified query complexity.")
            return IntentResult(intent=intent_val, confidence=conf, reason=reason)
        return None

    async def classify(self, message: str, context: Optional[str] = None) -> IntentResult:
        """
        Classifies message into CHAT or SOLVE with confidence and reasoning.
        The simple/complex decision is authoritative grounded in backend.core.router.route_request().
        """
        cleaned = (message or "").strip()
        if not cleaned:
            return IntentResult(intent="chat", confidence=1.0, reason="Empty message defaults to chat.")

        # 1. Deterministic SOLVE checks (high complexity patterns)
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

        # Context-aware conversational follow-up resolution
        if context and word_count < 25:
            followup_cues = (
                "what am i", "what is he", "what is she", "what are we", "what is it",
                "who is", "who am i", "what project", "what startup", "what name",
                "what was", "what did", "tell me more", "how about", "why that", "is it", "can it"
            )
            has_followup_pronouns = any(
                re.search(r"\b" + re.escape(w) + r"\b", cleaned.lower())
                for w in ("it", "that", "this", "he", "she", "they", "him", "her", "my", "i", "we")
            )
            if any(c in cleaned.lower() for c in followup_cues) or has_followup_pronouns:
                reason = "Conversational follow-up evaluated within existing conversation context."
                logger.info(f"[INTENT ROUTER] Intent: CHAT ({reason})")
                return IntentResult(intent="chat", confidence=0.97, reason=reason)

        # 3. Grounding in Authoritative Core Router
        decision = route_request(cleaned, context=context)

        # 4. LLM Classification fallback for boundary queries
        # CRITICAL: On ANY LLM failure (HTTP 429 quota exhaustion, timeout, provider error),
        # NEVER downgrade a complex query to chat. The authoritative core router decision is strictly enforced.
        try:
            llm_result = await self._classify_with_llm(cleaned)
            if llm_result:
                # If LLM suggests chat but core router classified query as COMPLEX, core router wins
                if llm_result.intent == "chat" and decision.route == ROUTE_COMPLEX:
                    logger.warning(
                        "[INTENT ROUTER] LLM suggested 'chat' but authoritative core router "
                        "classified query as COMPLEX. Preserving SOLVE."
                    )
                    return IntentResult(
                        intent="solve",
                        confidence=decision.confidence,
                        reason=f"Core router: {decision.reasoning}",
                    )
                logger.info(f"[INTENT ROUTER] Intent: {llm_result.intent.upper()} (LLM classified, confidence={llm_result.confidence})")
                return llm_result
        except Exception as exc:
            logger.warning(
                f"[INTENT ROUTER] LLM classifier failure / quota error ({exc}). "
                f"Grounding with authoritative core router."
            )

        # 5. Authoritative simple/complex decision from backend.core.router
        if decision.route == ROUTE_COMPLEX:
            logger.info(f"[INTENT ROUTER] Intent: SOLVE (Core router: {decision.reasoning})")
            return IntentResult(
                intent="solve",
                confidence=decision.confidence,
                reason=f"Core router: {decision.reasoning}",
            )

        if decision.route == ROUTE_SIMPLE:
            logger.info(f"[INTENT ROUTER] Intent: CHAT (Core router: {decision.reasoning})")
            return IntentResult(
                intent="chat",
                confidence=decision.confidence,
                reason=f"Core router: {decision.reasoning}",
            )

        reason = "Default conversational path for standard query."
        logger.info(f"[INTENT ROUTER] Intent: CHAT (Default fallback)")
        return IntentResult(intent="chat", confidence=0.80, reason=reason)


# Global singleton instance
intent_router = IntentRouter()
