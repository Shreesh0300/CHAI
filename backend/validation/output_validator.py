"""
CHAI Output Validator.

The structural and operational output gate in CHAI.
Evaluates final generated text for structural integrity, completeness,
format compliance, operational delivery readiness, and prevention of credential/error leakage.

Separation of Concerns:
- Reliability Monitor asks: "Is this generated result reliable enough to proceed?" (reasoning-quality gate)
- Output Validator asks: "Is the final output structurally and operationally valid?" (format/safety/transport gate)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.shared.logger import get_logger

logger = get_logger(__name__)

# Standard output length bounds
DEFAULT_MAX_OUTPUT_LENGTH: int = 50000
MIN_OUTPUT_LENGTH: int = 1

# Known high-entropy credential patterns (actual secret leaks, not educational mentions)
_CREDENTIAL_PATTERNS = [
    # Google API Key
    re.compile(r"\bAIzaSy[A-Za-z0-9_-]{25,}\b"),
    # OpenAI API Key (secret key format)
    re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{32,}\b"),
    # GitHub Personal Access Token
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b"),
    # AWS Access Key ID
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # Private Key blocks
    re.compile(r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----"),
    # Actual JWT token (header.payload.signature)
    re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b"),
    # Actual Bearer token with long random value (ignoring common placeholders)
    re.compile(r"\bBearer\s+(?!<|YOUR_|my_token|xxx|placeholder)[A-Za-z0-9_\-\.]{36,}\b", re.IGNORECASE),
    # Hardcoded sensitive variable assignments with long secret-like literals
    re.compile(r"""(?:api_key|secret_key|private_key|auth_token)\s*=\s*['\"][A-Za-z0-9_\-]{24,}['\"]""", re.IGNORECASE),
]

# Internal traceback and stack frame patterns
_TRACEBACK_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\):"),
    re.compile(r"""File\s+['"](?:.*?[\\/])?backend[\\/].*?['"],\s+line\s+\d+,\s+in\s+"""),
    re.compile(r"""File\s+['"].*?\.py['"],\s+line\s+\d+,\s+in\s+"""),
]

# Raw internal object string representation patterns
_RAW_OBJECT_PATTERNS = [
    re.compile(r"<[a-zA-Z_][a-zA-Z0-9_.]* object at 0x[0-9a-fA-F]+>"),
    re.compile(r"<function [a-zA-Z_][a-zA-Z0-9_.]* at 0x[0-9a-fA-F]+>"),
]


class OutputValidationResult(BaseModel):
    """Result of structural and operational validation."""
    is_valid: bool = Field(default=True, description="Whether output passed structural and operational validation.")
    errors: List[str] = Field(default_factory=list, description="Validation errors preventing output delivery.")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal validation warnings.")
    sanitized_output: Optional[str] = Field(None, description="Sanitized final deliverable text.")
    validation_metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic validation metadata.")

    @property
    def valid(self) -> bool:
        """Alias property for is_valid to adhere to common validation result semantics."""
        return self.is_valid

    @property
    def issues(self) -> List[str]:
        """Alias property for errors to adhere to common validation result semantics."""
        return self.errors


class OutputValidator:
    """Structural and operational output validation gate for CHAI deliverables."""

    def __init__(
        self,
        max_length: int = DEFAULT_MAX_OUTPUT_LENGTH,
        min_length: int = MIN_OUTPUT_LENGTH,
    ) -> None:
        self.max_length = max_length
        self.min_length = min_length

    def validate(
        self,
        output: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> OutputValidationResult:
        """Validate the candidate final output structurally and operationally.

        Parameters
        ----------
        output:
            The candidate final response text to be delivered.
        context:
            Optional workflow context or execution metadata.

        Returns
        -------
        OutputValidationResult
            Validation decision with errors, warnings, and sanitized text.
        """
        try:
            return self._do_validate(output, context)
        except Exception as exc:
            logger.error(f"OutputValidator internal execution error: {exc}")
            return OutputValidationResult(
                is_valid=False,
                errors=[f"Output validation internal error: {exc}"],
                warnings=[],
                sanitized_output=None,
                validation_metadata={"internal_error": str(exc)},
            )

    def _do_validate(
        self,
        output: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> OutputValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        # -------------------------------------------------------------
        # 1. Type Validation
        # -------------------------------------------------------------
        if output is None:
            return OutputValidationResult(
                is_valid=False,
                errors=["Final output is None."],
                sanitized_output=None,
                validation_metadata={"type": "NoneType"},
            )

        if not isinstance(output, str):
            return OutputValidationResult(
                is_valid=False,
                errors=[f"Expected string output, got {type(output).__name__}."],
                sanitized_output=None,
                validation_metadata={"type": type(output).__name__},
            )

        # -------------------------------------------------------------
        # 2. Emptiness & Whitespace Check
        # -------------------------------------------------------------
        trimmed = output.strip()
        if len(trimmed) < self.min_length:
            return OutputValidationResult(
                is_valid=False,
                errors=["Final output is empty or contains only whitespace."],
                sanitized_output="",
                validation_metadata={"length": 0},
            )

        # -------------------------------------------------------------
        # 3. Size Bounds Check
        # -------------------------------------------------------------
        if len(trimmed) > self.max_length:
            errors.append(f"Output exceeds maximum permitted length ({len(trimmed)} > {self.max_length}).")

        # Warning when approaching upper limit (90% threshold)
        if len(trimmed) > int(self.max_length * 0.9):
            warnings.append(f"Output length ({len(trimmed)} chars) approaches maximum threshold ({self.max_length}).")

        # -------------------------------------------------------------
        # 4. Null Byte / Malformed Payload Check
        # -------------------------------------------------------------
        if "\x00" in output:
            errors.append("Output contains corrupted null byte characters.")

        # Check for unformatted raw Python object dumps
        for obj_pattern in _RAW_OBJECT_PATTERNS:
            if obj_pattern.search(trimmed):
                errors.append("Output contains unformatted raw object dump representation.")
                break

        # -------------------------------------------------------------
        # 5. Operational Safety: Traceback / Internal Error Detection
        # -------------------------------------------------------------
        for tb_pattern in _TRACEBACK_PATTERNS:
            if tb_pattern.search(trimmed):
                errors.append("Output contains an unhandled Python exception traceback / stack trace.")
                break

        # -------------------------------------------------------------
        # 6. Operational Safety: Credential & Secret Leak Detection
        # -------------------------------------------------------------
        for cred_pattern in _CREDENTIAL_PATTERNS:
            match = cred_pattern.search(trimmed)
            if match:
                errors.append(f"Output contains potential credential or private key leakage matching security pattern: {cred_pattern.pattern[:20]}...")
                break

        # -------------------------------------------------------------
        # 7. Structural Formatting Warnings (Non-blocking)
        # -------------------------------------------------------------
        fence_count = trimmed.count("```")
        if fence_count % 2 != 0:
            warnings.append("Unclosed markdown code block fence detected.")

        is_valid = len(errors) == 0

        return OutputValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            sanitized_output=trimmed if is_valid else None,
            validation_metadata={
                "length": len(trimmed),
                "has_warnings": len(warnings) > 0,
                "error_count": len(errors),
            },
        )

    def is_valid(self, output: Any) -> bool:
        """Convenience method returning boolean validity."""
        return self.validate(output).is_valid
