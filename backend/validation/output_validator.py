"""
CHAI Output Validator Module.

Provides deterministic validation and sanitization of final synthesized outputs
before delivery to users or coordinator consumers.

Design Principles:
- Deterministic and fast; NOT another reasoning LLM agent.
- Validates completeness, structural integrity, and length sanity.
- Scans for and sanitizes sensitive credential patterns and internal error traces.
- Produces a canonical ValidationResult.
"""
from __future__ import annotations

import re
from typing import Optional, List, Dict, Any, Union

from backend.core.contracts import SynthesisResult, ValidationResult
from backend.shared.logger import get_logger

logger = get_logger(__name__)

# Patterns for sensitive tokens or credentials that must never leak in final responses
_SENSITIVE_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE),
    re.compile(r"Bearer\s+[a-zA-Z0-9\._\-]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE),
]

_TRACEBACK_PATTERN = re.compile(r"Traceback\s+\(most\s+recent\s+call\s+last\):", re.IGNORECASE)


class OutputValidator:
    """
    Deterministic validation engine for CHAI synthesis outputs.
    """

    def validate(
        self,
        synthesis: Union[SynthesisResult, Dict[str, Any], str],
        problem: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validates the synthesized output for structural integrity and safety.

        Args:
            synthesis: The SynthesisResult model, dict, or string to validate.
            problem: The original problem statement for context verification.

        Returns:
            ValidationResult with validation flags, issues list, and sanitized text.
        """
        logger.info("OutputValidator: validating synthesized output")
        issues: List[str] = []

        if synthesis is None:
            return ValidationResult(
                agent="output_validator",
                status="failed",
                is_valid=False,
                issues=["Synthesized result is None"],
                sanitized_text="Validation failed: null response.",
            )

        # Extract text and status
        if isinstance(synthesis, SynthesisResult):
            raw_text = synthesis.final_text or synthesis.reconciled_solution or synthesis.summary
            status = synthesis.status
        elif isinstance(synthesis, dict):
            raw_text = (
                synthesis.get("final_text")
                or synthesis.get("reconciled_solution")
                or synthesis.get("summary")
                or str(synthesis)
            )
            status = synthesis.get("status", "completed")
        else:
            raw_text = str(synthesis)
            status = "completed"

        # 1. Non-empty check
        cleaned = raw_text.strip()
        if not cleaned:
            issues.append("Synthesized output text is empty.")

        # 2. Status check
        if status != "completed":
            issues.append(f"Synthesis status is '{status}', expected 'completed'.")

        # 3. Minimum length check
        if len(cleaned) < 20 and cleaned:
            issues.append("Synthesized output is suspiciously short (< 20 characters).")

        # 4. Maximum length check (prevent runaway responses)
        if len(cleaned) > 100_000:
            issues.append("Synthesized output exceeds maximum allowed size (100,000 characters).")
            cleaned = cleaned[:100_000] + "\n\n[Truncated for length]"

        # 5. Traceback leak check
        if _TRACEBACK_PATTERN.search(cleaned):
            issues.append("Detected internal Python traceback in output.")
            cleaned = _TRACEBACK_PATTERN.sub("[Internal Error Trace Removed]", cleaned)

        # 6. Sensitive token check & sanitization
        sanitized = cleaned
        for pattern in _SENSITIVE_PATTERNS:
            if pattern.search(sanitized):
                issues.append("Detected potential credential or secret pattern in output.")
                sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)

        is_valid = len(issues) == 0

        return ValidationResult(
            agent="output_validator",
            status="completed" if is_valid or cleaned else "failed",
            is_valid=is_valid,
            issues=issues,
            sanitized_text=sanitized,
        )


__all__ = ["OutputValidator", "ValidationResult"]
