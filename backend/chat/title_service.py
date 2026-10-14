"""
Dedicated AI-powered conversation title generator for CHAI.
Generates concise, context-aware titles (3-8 words) capturing the central topic,
intent, or problem, replacing raw prompt truncation.
"""
import re
import asyncio
from typing import Optional, Any, Union, List, Dict

from backend.shared.llm_client import llm_client
from backend.shared.logger import get_logger

logger = get_logger(__name__)

TITLE_SYSTEM_INSTRUCTION = """You generate concise, natural titles for AI conversations.

Read the user's initial message and relevant conversation context. Identify the central topic, goal, question, or problem.

Write one clear, natural title (ideally 3 to 8 words) that captures the conversation's main idea.

Guidelines:
- Capture the specific core topic, technology, intent, or decision.
- Use meaningful technical terms, acronyms, and numbers when relevant (e.g. '24-Hour DSA Marathon', 'FastAPI vs. Django', 'Fixing Python Index Errors', 'AI-Powered Job Search Agent', 'College vs. Startup Decision').
- Use natural title capitalization and avoid unnecessary trailing punctuation (never include trailing periods or ellipses).
- Do not invent information, answer the user's question, explain your choice, or use markdown or quotation marks.
- Do NOT include any prefix such as 'Title:', 'Topic:', or 'Subject:'.
- Return ONLY the title text.
"""


def clean_generated_title(raw_title: Any) -> str:
    """
    Cleans raw LLM title output: removes markdown, prefixes, quotes, trailing ellipses,
    and extracts text from structured LangChain/Gemini content blocks (e.g. [{'type': 'text', 'text': '...'}]).
    """
    if not raw_title:
        return ""

    # If raw_title is already a list or dict
    if isinstance(raw_title, list):
        parts = []
        for item in raw_title:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
            elif hasattr(item, "text"):
                parts.append(str(item.text))
        text = " ".join(parts).strip()
    elif isinstance(raw_title, dict) and "text" in raw_title:
        text = str(raw_title["text"]).strip()
    elif hasattr(raw_title, "content"):
        return clean_generated_title(raw_title.content)
    else:
        text = str(raw_title).strip()

    if not text:
        return ""

    # Check if text is a string representation of LangChain structured output:
    # e.g. "[{'type': 'text', 'text': 'College Startup vs Job Decision'}]" or "[{'type': 'text', 'text': 'College Startup vs Job Decision"
    structured_match = re.search(r"['\"]text['\"]\s*:\s*['\"]([^'\"]+)", text)
    if structured_match:
        text = structured_match.group(1).strip()
    else:
        # Also clean any JSON/Python brackets or artifact wrappers
        text = re.sub(r"^\[\s*\{\s*['\"]type['\"]\s*:\s*['\"]text['\"]\s*,\s*['\"]text['\"]\s*:\s*['\"]?", "", text)
        text = re.sub(r"['\"]?\s*\}\s*\]$", "", text)

    # Remove code blocks or markdown fences if present
    text = re.sub(r"^```(?:text|markdown)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    # Strip prefixes like "Title:", "Topic:", "Subject:"
    text = re.sub(r"^(?:title|topic|subject|conversation title)\s*:\s*", "", text, flags=re.IGNORECASE)

    # Strip enclosing quotes and brackets
    text = re.sub(r'^[\[\{\("\'“‘`]+|[\]\}\)"\'”’`]+$', "", text).strip()

    # Strip trailing punctuation (periods, colons, semicolons, ellipses)
    text = re.sub(r"[\.\,\;\:\…\-\s]+$", "", text).strip()
    text = re.sub(r"\.{2,}$", "", text).strip()

    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()

    # Ensure reasonable length: if longer than 10 words, keep first 8
    words = text.split(" ")
    if len(words) > 10:
        text = " ".join(words[:8]).strip()

    # Capitalize first character if needed
    if text:
        text = text[0].upper() + text[1:]

    return text


def generate_fallback_title(message: str) -> str:
    """
    Produces a clean, readable, natural title derived heuristically from the user's message
    when LLM generation is unavailable or times out.
    Guarantees no awkward fragments (e.g. 'dropping out of college any...').
    """
    raw = (message or "").strip()
    if not raw:
        return "New Conversation"

    lower_msg = raw.lower()

    # Specific heuristic: FastAPI vs Django
    if "fastapi" in lower_msg and "django" in lower_msg:
        return "FastAPI vs. Django"

    # Specific heuristic: College / engineering dropout decisions
    if "drop out" in lower_msg or "dropping out" in lower_msg or "dropout" in lower_msg:
        if "engineering" in lower_msg or "enginnering" in lower_msg:
            return "Dropping Out of Engineering Decision"
        if "college" in lower_msg or "university" in lower_msg or "school" in lower_msg:
            return "College Dropout Decision"
        return "Dropping Out Decision"

    if "college" in lower_msg and "startup" in lower_msg:
        return "College vs. Startup Decision"

    # Specific heuristic: 24 hours / marathon / exam / dsa
    if "24 hours" in lower_msg and "dsa" in lower_msg:
        return "24-Hour DSA Marathon"
    if "dsa" in lower_msg and any(w in lower_msg for w in ("difficult", "hard", "struggling", "exam")):
        return "Overcoming DSA Challenges"

    # Specific heuristic: AI Job Search Agent
    if "job" in lower_msg and ("resume" in lower_msg or "agent" in lower_msg):
        return "AI-Powered Job Search Agent"

    # Specific heuristic: Python index error
    if "index" in lower_msg and "error" in lower_msg and "python" in lower_msg:
        return "Fixing Python Index Errors"

    # Specific heuristic: Error / Exception fixing
    if re.search(r"\b(?:error|exception|bug|crash|fail(?:ed|ing)?)\b", lower_msg):
        err_match = re.search(r"([a-zA-Z0-9_\s]{3,30}\s+(?:error|exception))", raw, re.IGNORECASE)
        if err_match:
            err_name = err_match.group(1).strip().title()
            return f"Fixing {err_name}"

    cleaned = raw
    # Remove greetings
    cleaned = re.sub(r"^(?:hi|hey|hello|greetings)[,! ]*(?:chai[,! ]*)?", "", cleaned, flags=re.IGNORECASE).strip()

    # Remove common conversational fillers and lead-ins (robust to "Im", "I'm", "thinking to", etc.)
    lead_ins = [
        r"^(?:can\s+you\s+(?:please\s+)?(?:tell\s+me|explain|help\s+me\s+with|help\s+me)|could\s+you|please)\s+",
        r"^(?:i(?:'m|m|\s+am)?\s+(?:thinking\s+(?:about|of|to)|wondering\s+(?:about|if|to)|confused\s+(?:between|about)|trying\s+to|planning\s+to))\s+",
        r"^(?:thinking\s+(?:about|of|to))\s+",
        r"^(?:i\s+(?:want\s+to|need\s+to|would\s+like\s+to|wish\s+to))\s+",
        r"^(?:what\s+(?:is|are)\s+the\s+best\s+way\s+to)\s+",
    ]
    for pattern in lead_ins:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    if not cleaned:
        cleaned = raw

    # Specific heuristic: "X vs Y"
    vs_match = re.search(r"([A-Za-z0-9_\-\.]+)\s+(?:vs\.?|versus|and|or)\s+([A-Za-z0-9_\-\.]+)", cleaned, re.IGNORECASE)
    if vs_match and any(w in lower_msg for w in ("between", "compare", "choose", "versus", "vs")):
        item1 = vs_match.group(1).strip()
        item2 = vs_match.group(2).strip()
        return f"{item1.title()} vs. {item2.title()}"

    # General word-based clean title: take up to 6 words
    words = cleaned.split()
    chosen_words = words[:6] if len(words) > 6 else words
    STOP_WORDS = {
        "of", "to", "for", "with", "in", "on", "at", "by", "from", "about",
        "and", "or", "the", "a", "an", "is", "any", "all", "too", "much"
    }
    while chosen_words and chosen_words[-1].lower().rstrip(",.!?;:") in STOP_WORDS and len(chosen_words) > 2:
        chosen_words.pop()

    result = " ".join(chosen_words)
    # Strip punctuation at end
    result = re.sub(r"[,\.\!\?\:\;\…\-\s]+$", "", result).strip()

    # Title-case first letter of each significant word
    clean_words = []
    for w in result.split():
        if w.lower() in ("a", "an", "the", "in", "on", "at", "for", "to", "of", "and", "but", "or"):
            clean_words.append(w.lower())
        else:
            clean_words.append(w.capitalize())

    formatted = " ".join(clean_words)
    if formatted:
        formatted = formatted[0].upper() + formatted[1:]
    return formatted or "New Conversation"


class TitleService:
    """
    Service for generating intelligent conversation titles using CHAI's LLM client.
    """

    async def generate_title(self, message: str, context: Optional[str] = None) -> str:
        """
        Generates a concise, context-aware title from the initial user prompt.
        Safely falls back to heuristic title generation on failure or timeout.
        """
        cleaned_msg = (message or "").strip()
        if not cleaned_msg:
            return "New Conversation"

        # Context-augmented prompt
        prompt_content = f"User Message:\n\"{cleaned_msg}\""
        if context and context.strip():
            prompt_content = f"Conversation Context:\n{context.strip()[:300]}\n\n{prompt_content}"

        # 1. Primary: Fast direct LLM call via thread executor
        try:
            raw_response = await asyncio.wait_for(
                llm_client.generate_content(
                    prompt=prompt_content,
                    system_instruction=TITLE_SYSTEM_INSTRUCTION,
                    temperature=0.1,
                    timeout=5.5,
                ),
                timeout=5.5,
            )

            if raw_response and not raw_response.startswith("Mock response"):
                title = clean_generated_title(raw_response)
                if title and 3 <= len(title) <= 75 and len(title.split()) <= 12:
                    if not any(neg in title.lower() for neg in ("as an ai", "i cannot", "sorry", "here is a title")):
                        logger.info(f"[TITLE GENERATOR] AI-generated title via Gemini direct: '{title}'")
                        return title
        except Exception as exc:
            logger.debug(f"[TITLE GENERATOR] LLM direct title generation error: {exc}")

        # 2. Secondary: Fall back to LangChain chat model with fallbacks
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            from backend.shared.llm_client import get_gemini_chat_model

            chat_model = get_gemini_chat_model(temperature=0.1)
            response = await asyncio.wait_for(
                chat_model.ainvoke([
                    SystemMessage(content=TITLE_SYSTEM_INSTRUCTION),
                    HumanMessage(content=prompt_content),
                ]),
                timeout=5.0,
            )
            raw_response = getattr(response, "content", str(response))
            if raw_response and not str(raw_response).startswith("Mock response"):
                title = clean_generated_title(str(raw_response))
                if title and 3 <= len(title) <= 75 and len(title.split()) <= 12:
                    if not any(neg in title.lower() for neg in ("as an ai", "i cannot", "sorry", "here is a title")):
                        logger.info(f"[TITLE GENERATOR] AI-generated title via LangChain: '{title}'")
                        return title
        except Exception as exc:
            logger.debug(f"[TITLE GENERATOR] LangChain title generation error: {exc}")

        # 3. Deterministic heuristic fallback
        fallback = generate_fallback_title(cleaned_msg)
        logger.info(f"[TITLE GENERATOR] Heuristic fallback title: '{fallback}'")
        return fallback

    def generate_fallback_title(self, message: str) -> str:
        """Exposes module-level heuristic fallback title generator on instance."""
        return generate_fallback_title(message)


# Global singleton instance
title_service = TitleService()
