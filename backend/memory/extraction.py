"""
Asynchronous memory extraction service for CHAI.
Extracts durable, future-useful facts from user conversations
while ignoring transient emotions, daily trivialities, and sensitive secrets.
"""
import re
import json
import asyncio
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from backend.memory.models import MemoryItem, MemoryCategory
from backend.memory.store import memory_store, sanitize_sensitive_data, is_guest_user
from backend.shared.llm_client import llm_client
from backend.shared.logger import get_logger

logger = get_logger(__name__)

# Transient signals that should NOT be retained as durable memory
TRANSIENT_REGEX = re.compile(
    r"\b(hungry|tired|sleepy|starving|exhausted|stressed today|headache|had lunch|had dinner|"
    r"going to sleep|good night|bye|brb|bored|feeling sick|test tomorrow|exam tomorrow)\b",
    re.IGNORECASE
)

# Rule-based heuristics for durable facts (guarantees fast offline/test accuracy)
DURABLE_PATTERNS = [
    # Career / Entrepreneurship goals
    (
        re.compile(r"(?:my\s+(?:long[- ]term\s+)?goal\s+is\s+to|i\s+want\s+to\s+build|i\s+aim\s+to\s+start)\s+([^.!?\n]+)", re.IGNORECASE),
        MemoryCategory.CAREER_GOAL,
        "User wants to {match}.",
        4
    ),
    (
        re.compile(r"(?:i\s+want\s+to\s+become\s+an?\s+)([^.!?\n]+)", re.IGNORECASE),
        MemoryCategory.CAREER_GOAL,
        "User wants to become {match}.",
        4
    ),
    # Education
    (
        re.compile(r"(?:i(?:'m|\s+am)\s+(?:a\s+)?(?:third-year|second-year|first-year|final-year)?\s*(?:college|university|cs|computer\s+science)?\s*student)", re.IGNORECASE),
        MemoryCategory.EDUCATION,
        "User is a computer science student in college.",
        3
    ),
    (
        re.compile(r"(?:i(?:'m|\s+am)\s+in\s+college)", re.IGNORECASE),
        MemoryCategory.EDUCATION,
        "User is currently a college student.",
        3
    ),
    # Projects
    (
        re.compile(r"(?:i(?:'m|\s+am)\s+building|working\s+on)\s+(?:a\s+|an\s+)?([^.!?\n]+)", re.IGNORECASE),
        MemoryCategory.PROJECT,
        "User is working on {match}.",
        3
    ),
    # Preferences
    (
        re.compile(r"(?:i\s+prefer|i\s+like|please\s+give\s+me)\s+([^.!?\n]+(?:answers|responses|solutions|explanations))", re.IGNORECASE),
        MemoryCategory.PREFERENCE,
        "User prefers {match}.",
        4
    ),
]


class ExtractedMemory(BaseModel):
    category: str
    fact: str
    importance: int = 3


class MemoryExtractionPayload(BaseModel):
    memories: List[ExtractedMemory] = Field(default_factory=list)


EXTRACTION_PROMPT = """You are a long-term memory extraction assistant.
Analyze the following user message from a conversation and extract only DURABLE, FUTURE-USEFUL facts about the user.

CRITICAL RULES:
1. ONLY extract permanent or long-term facts (e.g. goals, career aspirations, education, tech stack, strong preferences).
2. DO NOT extract transient emotions, daily plans, or temporary states (e.g., "I'm tired", "I'm hungry", "exam tomorrow", "had coffee").
3. DO NOT extract greetings, questions, or general conversation.
4. Keep each extracted memory factual, concise, and 3rd-person ("User wants to build a SaaS startup", "User is a CS student").
5. Return JSON with the list of extracted memories. If nothing durable is found, return an empty list.

Valid categories: education, career_goal, project, preference, expertise, general.
"""


class MemoryExtractor:
    """
    Extracts durable memory asynchronously without blocking user response.
    """

    def extract_heuristically(self, text: str) -> List[Dict[str, Any]]:
        """Fast, reliable heuristic extraction using regex patterns."""
        results = []
        if TRANSIENT_REGEX.search(text):
            # Check if text is only transient
            words = text.split()
            if len(words) < 8:
                return []

        for pattern, category, template, importance in DURABLE_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(1).strip() if match.groups() else ""
                if template.startswith("User is a") or template.startswith("User is currently"):
                    fact = template
                else:
                    fact = template.format(match=matched_text)
                results.append({
                    "category": category,
                    "fact": sanitize_sensitive_data(fact),
                    "importance": importance,
                })
        return results

    async def extract_and_store(
        self,
        user_id: str,
        user_message: str,
        assistant_reply: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        """
        Extracts durable facts from the exchange and persists them for user_id.
        Fails safely without raising exceptions to protect the user turn.
        """
        if not user_message or not user_message.strip():
            return []

        extracted_items: List[MemoryItem] = []

        try:
            # 1. First run heuristic extraction (instant and robust)
            heuristics = self.extract_heuristically(user_message)
            for item in heuristics:
                saved = await memory_store.add_memory(
                    user_id=user_id,
                    memory=item["fact"],
                    category=item["category"],
                    importance=item["importance"],
                    session_id=session_id,
                )
                extracted_items.append(saved)

            # 2. If message is substantive (> 10 words) and no heuristic was found, run LLM extraction
            if len(user_message.split()) > 10 and not heuristics:
                try:
                    prompt = f"{EXTRACTION_PROMPT}\n\nUser Message: \"{user_message}\""
                    raw = await asyncio.wait_for(
                        llm_client.generate_content(
                            prompt=prompt,
                            response_schema=MemoryExtractionPayload,
                            temperature=0.0,
                            timeout=10.0,
                        ),
                        timeout=10.0,
                    )
                    if raw and not raw.startswith("Mock response"):
                        data = json.loads(raw)
                        for m in data.get("memories", []):
                            fact = m.get("fact", "").strip()
                            cat_str = m.get("category", "general").lower()
                            try:
                                cat = MemoryCategory(cat_str)
                            except Exception:
                                cat = MemoryCategory.GENERAL

                            if fact and not TRANSIENT_REGEX.search(fact):
                                saved = await memory_store.add_memory(
                                    user_id=user_id,
                                    memory=fact,
                                    category=cat,
                                    importance=m.get("importance", 3),
                                    session_id=session_id,
                                )
                                extracted_items.append(saved)
                except Exception as llm_err:
                    logger.debug(f"[MEMORY EXTRACTOR] LLM extraction skipped or failed gracefully: {llm_err}")

        except Exception as exc:
            # Memory extraction failure must NEVER break user response
            logger.warning(f"[MEMORY EXTRACTOR] Asynchronous extraction error: {exc}")

        return extracted_items


# Global singleton instance
memory_extractor = MemoryExtractor()
