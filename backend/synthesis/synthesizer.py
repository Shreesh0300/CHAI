"""
CHAI Multilingual Synthesizer.

Synthesizes validated findings from all specialized agents into a unified,
coherent, and actionable final answer in the user's requested/detected language:
  - English  ('en')
  - Hindi    ('hi')
  - Kannada  ('kn')

Policy:
  - Generates the human-readable answer in the target language.
  - Strictly preserves technical names, APIs, library names, code blocks,
    URLs, numbers, and proper nouns (e.g., FastAPI, React, Supabase, Python, SQL).
  - Provides deterministic, localized fallbacks when LLM execution is unavailable or offline.
"""

import asyncio
from typing import Dict, Any, List, Optional
from backend.core.language import LANGUAGE_NAMES, DEFAULT_LANGUAGE
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class Synthesizer:
    """
    Final synthesis layer for CHAI multi-agent responses.
    """

    def __init__(self, llm: Optional[Any] = None, model_name: Optional[str] = None):
        self._llm = llm
        self.model_name = model_name

    def _get_llm(self):
        """Lazily initialize chat model if configured."""
        if self._llm is not None:
            return self._llm

        try:
            from backend.shared.llm_client import get_gemini_chat_model, get_gemini_api_key
            api_key = get_gemini_api_key()
            if not api_key:
                return None
            self._llm = get_gemini_chat_model(model_name=self.model_name, api_key=api_key)
            if hasattr(self._llm, "max_retries"):
                self._llm.max_retries = 1
            return self._llm
        except Exception as e:
            logger.warning(f"Synthesizer LLM unavailable: {e}")
            return None

    async def synthesize(
        self,
        problem: str,
        agent_outputs: Dict[str, Any],
        detected_conflicts: Optional[List[str]] = None,
        language: str = DEFAULT_LANGUAGE,
        limitations: Optional[List[str]] = None,
    ) -> str:
        """
        Synthesizes agent outputs into the final answer in the requested language.
        """
        lang_code = (language or DEFAULT_LANGUAGE).lower()
        if lang_code not in LANGUAGE_NAMES:
            lang_code = DEFAULT_LANGUAGE

        conflicts = detected_conflicts or []
        limits = limitations or []

        # 1. Attempt LLM generation if available
        llm = self._get_llm()
        if llm:
            try:
                synthesized = await self._synthesize_with_llm(
                    llm=llm,
                    problem=problem,
                    agent_outputs=agent_outputs,
                    detected_conflicts=conflicts,
                    language=lang_code,
                    limitations=limits,
                )
                if synthesized and synthesized.strip():
                    return synthesized.strip()
            except Exception as e:
                logger.warning(f"LLM synthesis failed, falling back to structured synthesis: {e}")

        # 2. Resilient localized structured fallback
        return self._synthesize_fallback(
            agent_outputs=agent_outputs,
            detected_conflicts=conflicts,
            language=lang_code,
            limitations=limits,
        )

    async def _synthesize_with_llm(
        self,
        llm: Any,
        problem: str,
        agent_outputs: Dict[str, Any],
        detected_conflicts: List[str],
        language: str,
        limitations: List[str],
    ) -> str:
        """Invokes Gemini LLM for natural multilingual synthesis."""
        from langchain_core.messages import SystemMessage, HumanMessage

        lang_name = LANGUAGE_NAMES.get(language, "English")

        system_instruction = (
            f"You are the final CHAI synthesizer.\n"
            f"The user's requested language is {lang_name} ('{language}').\n\n"
            f"Synthesize the validated findings from all specialized agents into one coherent, actionable answer.\n"
            f"Return the final human-readable answer entirely in {lang_name}.\n\n"
            f"STRICT RULES:\n"
            f"- Preserve technical names, libraries, framework names, and tools in English (e.g. FastAPI, LangGraph, LangChain, Supabase, React, Python, REST, SQL, API).\n"
            f"- Preserve code blocks, URLs, identifiers, numbers, and metrics verbatim.\n"
            f"- Do not translate code.\n"
            f"- Do not invent information beyond agent outputs.\n"
            f"- Clearly present Strategy, Architecture, Security, and Tradeoffs in a well-structured format.\n"
            f"- If the language is Kannada ('kn'), produce natural Kannada sentences while keeping technical keywords recognizable.\n"
            f"- If the language is Hindi ('hi'), produce natural Hindi sentences while keeping technical keywords recognizable.\n"
            f"- If the language is English ('en'), produce fluent English."
        )

        strat_text = (
            agent_outputs.get("strategist", {}).get("strategy")
            or agent_outputs.get("strategist", {}).get("strategy_overview", "")
        )
        arch_text = agent_outputs.get("engineer", {}).get("technical_architecture", "")
        sec_text = agent_outputs.get("security", {}).get("security_summary", "")

        conflicts_str = "\n".join(f"- {c}" for c in detected_conflicts) if detected_conflicts else "None"
        limits_str = "\n".join(f"- {l}" for l in limitations) if limitations else "None"

        user_content = (
            f"User Problem: {problem}\n"
            f"Target Language: {lang_name} ({language})\n\n"
            f"Agent Findings:\n"
            f"- Strategy: {strat_text}\n"
            f"- Technical Architecture: {arch_text}\n"
            f"- Security Assessment: {sec_text}\n"
            f"- Identified Tradeoffs / Inconsistencies: {conflicts_str}\n"
            f"- Limitations: {limits_str}\n\n"
            f"Produce the final unified response in {lang_name}:"
        )

        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=user_content),
        ]

        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=12.0)
        return getattr(response, "content", str(response))

    def _synthesize_fallback(
        self,
        agent_outputs: Dict[str, Any],
        detected_conflicts: List[str],
        language: str,
        limitations: List[str],
    ) -> str:
        """
        Deterministic, localized fallback templates for English, Hindi, and Kannada.
        Ensures the system never crashes or fails even under high load or network partition.
        """
        strat_text = (
            agent_outputs.get("strategist", {}).get("strategy")
            or agent_outputs.get("strategist", {}).get("strategy_overview", "")
        )
        arch_text = agent_outputs.get("engineer", {}).get("technical_architecture", "")
        sec_text = agent_outputs.get("security", {}).get("security_summary", "")

        if language == "kn":
            res = "ನಮ್ಮ ವಿಶೇಷ ಏಜೆಂಟ್‌ಗಳ ಸಮಗ್ರ ವಿಶ್ಲೇಷಣೆಯ ಆಧಾರದ ಮೇಲೆ:\n"
            if strat_text:
                res += f"\nತಂತ್ರಗಾರಿಕೆ (Strategy):\n{strat_text}\n"
            if arch_text:
                res += f"\nತಾಂತ್ರಿಕ ವಿನ್ಯಾಸ (Architecture):\n{arch_text}\n"
            if sec_text:
                res += f"\nಭದ್ರತಾ ಮೌಲ್ಯಮಾಪನ (Security Assessment):\n{sec_text}\n"
            if detected_conflicts:
                res += f"\nಗುರುತಿಸಲಾದ ಅಸಂಗತತೆಗಳು ಮತ್ತು ಹೊಂದಾಣಿಕೆಗಳು (Tradeoffs):\n" + "\n".join(
                    f"- {c}" for c in detected_conflicts
                ) + "\n"
            if limitations:
                res += f"\nಮಿತಿಗಳು (Limitations):\n" + "\n".join(
                    f"- {l}" for l in limitations
                ) + "\n"
            return res

        elif language == "hi":
            res = "हमारे विशेषज्ञ एजेंटों के व्यापक विश्लेषण के आधार पर:\n"
            if strat_text:
                res += f"\nरणनीति (Strategy):\n{strat_text}\n"
            if arch_text:
                res += f"\nवास्तुशिल्प (Architecture):\n{arch_text}\n"
            if sec_text:
                res += f"\nसुरक्षा मूल्यांकन (Security Assessment):\n{sec_text}\n"
            if detected_conflicts:
                res += f"\nपहचानी गई विसंगतियां और व्यापार-बंद (Tradeoffs):\n" + "\n".join(
                    f"- {c}" for c in detected_conflicts
                ) + "\n"
            if limitations:
                res += f"\nसीमाएं (Limitations):\n" + "\n".join(
                    f"- {l}" for l in limitations
                ) + "\n"
            return res

        else:  # default 'en'
            res = "Based on the comprehensive analysis of our specialized agents:\n"
            if strat_text:
                res += f"\nStrategy:\n{strat_text}\n"
            if arch_text:
                res += f"\nArchitecture:\n{arch_text}\n"
            if sec_text:
                res += f"\nSecurity Assessment:\n{sec_text}\n"
            if detected_conflicts:
                res += f"\nIdentified Inconsistencies / Tradeoffs:\n" + "\n".join(
                    f"- {c}" for c in detected_conflicts
                ) + "\n"
            if limitations:
                res += f"\nLimitations:\n" + "\n".join(
                    f"- {l}" for l in limitations
                ) + "\n"
            return res
