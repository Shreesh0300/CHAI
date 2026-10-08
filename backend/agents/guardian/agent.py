"""
CHAI Guardian Agent — core implementation.

Uses the shared ``GeminiClient`` (``backend.shared.llm_client``) to generate
a structured safety, ethics, privacy, and responsible-use analysis. Returns a
``GuardianOutput`` (backward-compatible with the Coordinator) that embeds a
canonical ``GuardianResult``.

Design principles:
- Reuses the shared project singleton ``llm_client``.
- Anti-prompt-injection isolation for reference context.
- Bounded context serialization with truncation protections.
- Bounded retry logic (max 2 attempts).
- Tolerant JSON parsing supporting markdown fences and surrounding text.
- Graceful degradation returning ``status=failed`` rather than crashing the pipeline.
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional, Any

from backend.shared.llm_client import llm_client
from backend.shared.logger import get_logger
from backend.agents.guardian.prompts import (
    SYSTEM_PROMPT,
    REFERENCE_CONTEXT_HEADER,
    GUARDIAN_TASK_INSTRUCTION,
)
from backend.agents.guardian.schemas import (
    AgentStatus,
    RiskLevel,
    GuardianResult,
    GuardianOutput,
)

logger = get_logger(__name__)

# Maximum number of LLM call attempts (initial + retry).
_MAX_ATTEMPTS: int = 2

# Maximum characters allowed for reference context to bound prompt size.
_MAX_CONTEXT_CHARS: int = 4000


class GuardianAgent:
    """CHAI Guardian Agent — safety, ethics, privacy, and responsible AI specialist."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.system_prompt: str = SYSTEM_PROMPT
        self._llm_client = llm_client

    # ------------------------------------------------------------------
    # Public interface consumed by the Coordinator
    # ------------------------------------------------------------------

    async def run(
        self,
        problem: str,
        context: Optional[dict] = None,
    ) -> GuardianOutput:
        """Analyse *problem* from a safety perspective and return ``GuardianOutput``.

        Parameters
        ----------
        problem:
            The user's problem statement or query.
        context:
            Optional reference outputs from other CHAI agents (Engineer,
            Strategist, Researcher). Treated strictly as untrusted data.

        Returns
        -------
        GuardianOutput
            Backward-compatible model consumed by the Coordinator with the full
            canonical ``GuardianResult`` embedded inside.
        """
        start_time = time.monotonic()
        has_context = bool(context)
        logger.info(f"Guardian Agent: starting analysis (context_provided={has_context}).")

        # ---- Input validation ----
        if not problem or not problem.strip():
            logger.warning("Guardian Agent: received empty problem.")
            return self._make_failed_output("Empty problem provided. Cannot perform safety analysis.")

        # ---- Build LLM prompt ----
        user_prompt = self._build_user_prompt(problem, context)

        # ---- Call LLM with bounded retry ----
        client = self._llm_client or llm_client
        last_error: Optional[Exception] = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response_text = await client.generate_content(
                    prompt=user_prompt,
                    system_instruction=self.system_prompt,
                )

                # Handle mock mode (API key not configured)
                if "Mock response" in response_text:
                    logger.info("Guardian Agent: LLM returned mock response (no API key).")
                    return self._make_mock_output(problem)

                # Parse and validate
                result = self._parse_response(response_text)

                elapsed = time.monotonic() - start_time
                logger.info(f"Guardian Agent: completed in {elapsed:.2f}s (attempt {attempt}).")
                return GuardianOutput.from_guardian_result(result)

            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"Guardian Agent: attempt {attempt}/{_MAX_ATTEMPTS} failed — {exc!r}"
                )

        # All attempts exhausted
        logger.error(f"Guardian Agent: all {_MAX_ATTEMPTS} attempts failed. Last error: {last_error!r}")
        return self._make_failed_output(
            f"Guardian Agent failed after {_MAX_ATTEMPTS} attempts: {last_error}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_serialize_context(
        context: Optional[dict],
        max_chars: int = _MAX_CONTEXT_CHARS,
    ) -> Optional[str]:
        """Safely serialize context dict to a bounded JSON string.

        Guarantees:
        - None or empty context returns None.
        - Non-dict values return None.
        - Non-JSON-serializable objects (custom instances, dates, sets) are
          converted safely via ``str`` without raising exceptions.
        - Circular references or unexpected exceptions fallback cleanly.
        - Payloads exceeding ``max_chars`` are truncated with a visible notice.
        """
        if not context or not isinstance(context, dict):
            return None

        try:
            serialized = json.dumps(context, default=str, indent=2)
        except Exception:
            try:
                serialized = str({str(k): str(v) for k, v in context.items()})
            except Exception:
                serialized = "[Context serialization unavailable]"

        if len(serialized) > max_chars:
            serialized = (
                serialized[:max_chars]
                + f"\n... [TRUNCATED: context exceeded maximum limit of {max_chars} characters]"
            )

        return serialized

    @classmethod
    def _build_user_prompt(cls, problem: str, context: Optional[dict]) -> str:
        """Construct the user-facing prompt sent to the LLM.

        Clearly separates:
        1. Original user problem (explicitly labeled)
        2. Reference context from other CHAI agents (untrusted reference data)
        3. Actual Guardian task (with safety role boundaries re-asserted)
        """
        parts = [f"PROBLEM:\n{problem.strip()}"]

        context_str = cls._safe_serialize_context(context)
        if context_str:
            parts.append(f"{REFERENCE_CONTEXT_HEADER}\n\n{context_str}")

        parts.append(GUARDIAN_TASK_INSTRUCTION)
        return "\n\n".join(parts)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from raw LLM text, tolerating markdown fences."""
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            return brace_match.group(0)
        return text

    def _parse_response(self, response_text: str) -> GuardianResult:
        """Parse raw LLM text into a validated ``GuardianResult``."""
        json_str = self._extract_json(response_text)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM output is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")

        try:
            return GuardianResult(**data)
        except Exception as exc:
            raise ValueError(f"Schema validation failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Fallback builders
    # ------------------------------------------------------------------

    @staticmethod
    def _make_failed_output(error_message: str) -> GuardianOutput:
        """Return a minimal ``GuardianOutput`` representing a failure."""
        result = GuardianResult(
            agent="guardian",
            status=AgentStatus.FAILED,
            safety_assessment=error_message,
            risk_level=RiskLevel.LOW,
        )
        return GuardianOutput.from_guardian_result(result)

    @staticmethod
    def _make_mock_output(problem: str) -> GuardianOutput:
        """Return a plausible mock ``GuardianOutput`` when no API key is set."""
        result = GuardianResult(
            agent="guardian",
            status=AgentStatus.COMPLETED,
            safety_assessment=f"[Mock] Safety and responsible-use analysis of: {problem}",
            risk_level=RiskLevel.LOW,
            safety_risks=[],
            ethical_risks=[],
            privacy_considerations=["[Mock] Ensure appropriate privacy practices are observed."],
            misuse_risks=["[Mock] Monitor system for unintended usage."],
            safeguards=["[Mock] Disclose AI limitations to end users."],
            responsible_use_guidelines=["[Mock] Operate in compliance with responsible AI principles."],
            assumptions=["[Mock] No live LLM available; returning placeholder safety data."],
            missing_information=["[Mock] Detailed safety analysis requires GEMINI_API_KEY."],
        )
        return GuardianOutput.from_guardian_result(result)
