"""
CHAI Engineer Agent — core implementation.

Uses the shared ``GeminiClient`` (``backend.shared.llm_client``) to generate
a structured technical analysis for a given problem.  Returns an
``EngineerOutput`` (backward-compatible with the Coordinator) that wraps a
rich ``EngineerResult``.

Design decisions
~~~~~~~~~~~~~~~~
* **No duplicate LLM client** — reuses the project singleton.
* **Bounded retry** — at most 1 retry on transient LLM / parse failures.
* **Structured logging** — via the project's shared logger.
* **JSON extraction** — tolerates markdown-fenced JSON from the LLM.
* **Graceful degradation** — returns ``status=failed`` instead of crashing
  the entire CHAI pipeline on unrecoverable errors.
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from backend.shared.llm_client import llm_client
from backend.shared.logger import get_logger
from backend.agents.engineer.prompts import (
    SYSTEM_PROMPT,
    REFERENCE_CONTEXT_HEADER,
    ENGINEERING_TASK_INSTRUCTION,
)
from backend.agents.engineer.schemas import (
    AgentStatus,
    EngineerResult,
    EngineerOutput,
)

logger = get_logger(__name__)

# Maximum number of LLM call attempts (initial + retries).
_MAX_ATTEMPTS: int = 2

# Maximum characters allowed for reference context to prevent prompt explosion.
_MAX_CONTEXT_CHARS: int = 4000


class EngineerAgent:
    """CHAI Engineer Agent — technical / engineering analysis specialist."""

    def __init__(self, llm_client: Any = None) -> None:
        self.system_prompt: str = SYSTEM_PROMPT
        self.llm_client = llm_client

    # ------------------------------------------------------------------
    # Public interface consumed by the Coordinator
    # ------------------------------------------------------------------

    async def run(
        self,
        problem: str,
        context: Optional[dict] = None,
    ) -> EngineerOutput:
        """Analyse *problem* and return a structured ``EngineerOutput``.

        Parameters
        ----------
        problem:
            The user's problem statement or query.
        context:
            Optional dict with outputs from prior agents (researcher,
            strategist, etc.).  Forwarded verbatim to the LLM prompt.

        Returns
        -------
        EngineerOutput
            Backward-compatible model consumed by the Coordinator.  The
            full ``EngineerResult`` is embedded inside
            ``EngineerOutput.engineer_result``.
        """
        start_time = time.monotonic()
        has_context = bool(context)
        logger.info(f"Engineer Agent: starting analysis (context_provided={has_context}).")

        # ---- Input validation ----
        if not problem or not problem.strip():
            logger.warning("Engineer Agent: received empty problem.")
            return self._make_failed_output("Empty problem provided. Cannot perform technical analysis.")

        # ---- Build LLM prompt ----
        user_prompt = self._build_user_prompt(problem, context)

        # ---- Call LLM with bounded retry ----
        last_error: Optional[Exception] = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                current_prompt = user_prompt
                if attempt > 1 and last_error:
                    clean_err = str(last_error).split("\n")[0]
                    missing_hints = []
                    err_str = str(last_error).lower()
                    if "ai_ml_design" in err_str or "overview" in err_str:
                        missing_hints.append("- Populating 'overview' in 'ai_ml_design' (e.g. 'overview': 'AI/ML subsystem overview')")
                    if "architecture" in err_str:
                        missing_hints.append("- Populating 'overview' in 'architecture'")
                    if "database" in err_str:
                        missing_hints.append("- Populating 'overview' in 'database_design'")
                    if "problem_understanding" in err_str:
                        missing_hints.append("- Mandatory 'problem_understanding' must be non-empty")
                    hints_block = ("\nSpecific corrections required:\n" + "\n".join(missing_hints)) if missing_hints else ""

                    current_prompt = (
                        f"{user_prompt}\n\n"
                        f"CRITICAL CONTRACT CORRECTION (ATTEMPT {attempt}):\n"
                        f"Your previous response failed schema validation: {clean_err}\n"
                        f"You MUST return strictly valid JSON matching the EngineerResult schema.{hints_block}\n"
                        f"Ensure every required field is present and non-empty. Specifically:\n"
                        f"- 'problem_understanding' is mandatory.\n"
                        f"- If 'ai_ml_design' is included, 'overview' is strictly required.\n"
                        f"- If 'architecture' is included, 'overview' is strictly required.\n"
                        f"- If 'database_design' is included, 'overview' is strictly required.\n"
                        f"- 'agent' MUST be 'engineer' and 'status' MUST be 'completed'.\n"
                        f"Output ONLY the JSON object."
                    )

                client_to_use = self.llm_client or llm_client
                try:
                    response_text = await client_to_use.generate_content(
                        prompt=current_prompt,
                        system_instruction=self.system_prompt,
                        response_schema=EngineerResult,
                    )
                except Exception as struct_err:
                    err_str = str(struct_err)
                    if "[QUOTA_ERROR]" in err_str or "[AUTH_ERROR]" in err_str:
                        raise
                    logger.warning(f"Engineer structured schema call failed, trying raw prompt fallback: {err_str}")
                    response_text = await client_to_use.generate_content(
                        prompt=current_prompt,
                        system_instruction=self.system_prompt,
                    )

                # Handle mock mode (API key not configured)
                if "Mock response" in response_text:
                    logger.info("Engineer Agent: LLM returned mock response (no API key).")
                    return self._make_mock_output(problem)

                # Parse and validate
                result = self._parse_response(response_text)

                elapsed = time.monotonic() - start_time
                logger.info(f"Engineer Agent: completed in {elapsed:.2f}s (attempt {attempt}).")
                return EngineerOutput.from_engineer_result(result)

            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"Engineer Agent: attempt {attempt}/{_MAX_ATTEMPTS} failed — {exc!r}"
                )

        # All attempts exhausted
        logger.error(f"Engineer Agent: all {_MAX_ATTEMPTS} attempts failed. Last error: {last_error!r}")
        clean_msg = str(last_error).split("\n")[0] if last_error else "Unknown error"
        return self._make_failed_output(
            f"Engineer Agent failed after {_MAX_ATTEMPTS} attempts: {clean_msg}"
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
        3. Actual engineering task (with role boundaries re-asserted)
        """
        parts = [f"PROBLEM:\n{problem.strip()}"]

        context_str = cls._safe_serialize_context(context)
        if context_str:
            parts.append(f"{REFERENCE_CONTEXT_HEADER}\n\n{context_str}")

        parts.append(ENGINEERING_TASK_INSTRUCTION)
        return "\n\n".join(parts)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from raw LLM text, tolerating markdown fences."""
        # Try ```json ... ``` first
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        # Fall back to the first { … } block
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            return brace_match.group(0)
        return text

    def _parse_response(self, response_text: str) -> EngineerResult:
        """Parse raw LLM text into a validated ``EngineerResult``."""
        json_str = self._extract_json(response_text)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM output is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")

        try:
            return EngineerResult(**data)
        except Exception as exc:
            raise ValueError(f"Schema validation failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Fallback builders
    # ------------------------------------------------------------------

    @staticmethod
    def _make_failed_output(error_message: str) -> EngineerOutput:
        """Return a minimal ``EngineerOutput`` representing a failure."""
        result = EngineerResult(
            agent="engineer",
            status=AgentStatus.FAILED,
            problem_understanding=error_message,
        )
        output = EngineerOutput.from_engineer_result(result)
        return output

    @staticmethod
    def _make_mock_output(problem: str) -> EngineerOutput:
        """Return a plausible mock ``EngineerOutput`` when no API key is set."""
        result = EngineerResult(
            agent="engineer",
            status=AgentStatus.COMPLETED,
            problem_understanding=f"[Mock] Technical analysis of: {problem}",
            functional_requirements=["[Mock] Requirement analysis pending — API key not configured."],
            assumptions=["[Mock] No live LLM available; returning placeholder data."],
            missing_information=["[Mock] Full analysis requires a configured GEMINI_API_KEY."],
        )
        return EngineerOutput.from_engineer_result(result)
