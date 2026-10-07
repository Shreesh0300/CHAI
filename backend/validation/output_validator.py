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
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from backend.core.contracts import SynthesisResult, ValidationResult as ContractValidationResult
from backend.shared.logger import get_logger

logger = get_logger(__name__)

# Standard output length bounds
DEFAULT_MAX_OUTPUT_LENGTH: int = 50000
MIN_OUTPUT_LENGTH: int = 1

# Known high-entropy credential patterns (actual secret leaks, not educational mentions)
_CREDENTIAL_PATTERNS = [
    # Google API Key
    re.compile(r"\bAIzaSy[A-Za-z0-9_-]{25,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"),
    # OpenAI API Key (secret key format)
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b"),
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
    re.compile(r"\bBearer\s+(?!<|YOUR_|my_token|xxx|placeholder)[A-Za-z0-9_\-\.]{20,}\b", re.IGNORECASE),
    # Hardcoded sensitive variable assignments with long secret-like literals
    re.compile(r"""(?:api_key|secret_key|private_key|auth_token)\s*=\s*['\"][A-Za-z0-9_\-]{24,}['\"]""", re.IGNORECASE),
]

# Internal traceback and stack frame patterns
_TRACEBACK_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
    re.compile(r"""File\s+['"](?:.*?[\\/])?backend[\\/].*?['"],\s+line\s+\d+,\s+in\s+"""),
    re.compile(r"""File\s+['"].*?\.py['"],\s+line\s+\d+,\s+in\s+"""),
]

# Raw internal object string representation patterns
_RAW_OBJECT_PATTERNS = [
    re.compile(r"<[a-zA-Z_][a-zA-Z0-9_.]* object at 0x[0-9a-fA-F]+>"),
    re.compile(r"<function [a-zA-Z_][a-zA-Z0-9_.]* at 0x[0-9a-fA-F]+>"),
]


class OutputValidationResult(ContractValidationResult):
    """Result of structural and operational validation."""
    agent: str = Field(default="output_validator", description="Agent identifier")
    status: str = Field(default="completed", description="Execution status ('completed' or 'failed')")
    is_valid: bool = Field(default=True, description="Whether output passed structural and operational validation.")
    errors: List[str] = Field(default_factory=list, description="Validation errors preventing output delivery.")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal validation warnings.")
    issues: List[str] = Field(default_factory=list, description="Identified validation issues or errors.")
    sanitized_output: Optional[str] = Field(None, description="Sanitized final deliverable text.")
    sanitized_text: str = Field(default="", description="Sanitized final text for contract compatibility.")
    validation_metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic validation metadata.")

    def model_post_init(self, __context: Any) -> None:
        if not self.issues and self.errors:
            self.issues = list(self.errors)
        elif not self.errors and self.issues:
            self.errors = list(self.issues)
        if not self.sanitized_text and self.sanitized_output:
            self.sanitized_text = self.sanitized_output

    @property
    def valid(self) -> bool:
        """Alias property for is_valid to adhere to common validation result semantics."""
        return self.is_valid


# Alias for backward compatibility
ValidationResult = OutputValidationResult


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
        output: Any = None,
        context: Optional[Dict[str, Any]] = None,
        *,
        synthesis: Any = None,
        problem: Optional[str] = None,
    ) -> OutputValidationResult:
        """Validate candidate output structurally and operationally."""
        try:
            return self._do_validate(output=output, context=context, synthesis=synthesis, problem=problem)
        except Exception as exc:
            logger.error(f"OutputValidator internal execution error: {exc}")
            return OutputValidationResult(
                agent="output_validator",
                status="failed",
                is_valid=False,
                errors=[f"Output validation internal error: {exc}"],
                warnings=[],
                issues=[f"Output validation internal error: {exc}"],
                sanitized_output=None,
                sanitized_text="Validation failed: internal error.",
                validation_metadata={"internal_error": str(exc)},
            )

    def _do_validate(
        self,
        output: Any = None,
        context: Optional[Dict[str, Any]] = None,
        *,
        synthesis: Any = None,
        problem: Optional[str] = None,
    ) -> OutputValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        # Determine target
        target = synthesis if synthesis is not None else output

        # -------------------------------------------------------------
        # 1. Type Validation
        # -------------------------------------------------------------
        if target is None:
            return OutputValidationResult(
                agent="output_validator",
                status="failed",
                is_valid=False,
                errors=["Final output is None."],
                issues=["Final output is None."],
                sanitized_output=None,
                sanitized_text="Validation failed: null response.",
                validation_metadata={"type": "NoneType"},
            )

        is_synthesis_model = False
        if isinstance(target, SynthesisResult):
            raw_text = target.final_text or target.reconciled_solution or target.summary or ""
            is_synthesis_model = True
        elif isinstance(target, str):
            raw_text = target
        else:
            return OutputValidationResult(
                agent="output_validator",
                status="failed",
                is_valid=False,
                errors=[f"Expected string output, got {type(target).__name__}."],
                issues=[f"Expected string output, got {type(target).__name__}."],
                sanitized_output=None,
                sanitized_text="",
                validation_metadata={"type": type(target).__name__},
            )

        # -------------------------------------------------------------
        # 2. Emptiness & Whitespace Check
        # -------------------------------------------------------------
        trimmed = raw_text.strip()
        if len(trimmed) < self.min_length:
            return OutputValidationResult(
                agent="output_validator",
                status="failed",
                is_valid=False,
                errors=["Final output is empty or contains only whitespace."],
                issues=["Final output is empty or contains only whitespace."],
                sanitized_output="" if trimmed == "" else None,
                sanitized_text="",
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
        if "\x00" in raw_text:
            errors.append("Output contains corrupted null byte characters.")

        # Check for unformatted raw Python object dumps
        for obj_pattern in _RAW_OBJECT_PATTERNS:
            if obj_pattern.search(trimmed):
                errors.append("Output contains unformatted raw object dump representation.")
                break

        # -------------------------------------------------------------
        # 5. Operational Safety: Traceback / Internal Error Detection
        # -------------------------------------------------------------
        sanitized = trimmed
        traceback_detected = False
        for tb_pattern in _TRACEBACK_PATTERNS:
            if tb_pattern.search(trimmed):
                traceback_detected = True
                errors.append("Output contains an unhandled Python exception traceback / stack trace.")
                sanitized = tb_pattern.sub("[Internal Error Trace Removed]", sanitized)
                break

        # -------------------------------------------------------------
        # 6. Operational Safety: Credential & Secret Leak Detection
        # -------------------------------------------------------------
        for cred_pattern in _CREDENTIAL_PATTERNS:
            match = cred_pattern.search(sanitized)
            if match:
                errors.append(
                    f"Output contains potential credential or private key leakage matching security pattern: {cred_pattern.pattern[:20]}..."
                )
                sanitized = cred_pattern.sub("[REDACTED_SECRET]", sanitized)

        # -------------------------------------------------------------
        # 7. Structural Formatting Warnings (Non-blocking)
        # -------------------------------------------------------------
        fence_count = trimmed.count("```")
        if fence_count % 2 != 0:
            warnings.append("Unclosed markdown code block fence detected.")

        is_valid = len(errors) == 0

        # When valid, sanitized_output is the clean text.
        # When invalid, sanitized_output is None (for test_output_validator.py),
        # but sanitized_text provides the redacted text (for contract tests like test_agent_workflow_contracts.py).
        sanitized_output = trimmed if is_valid else None
        sanitized_text = sanitized if not is_valid else trimmed

        return OutputValidationResult(
            agent="output_validator",
            status="completed" if is_valid or is_synthesis_model else "failed",
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            issues=list(errors),
            sanitized_output=sanitized_output,
            sanitized_text=sanitized_text,
            validation_metadata={
                "length": len(trimmed),
                "has_warnings": len(warnings) > 0,
                "error_count": len(errors),
            },
        )

    def is_valid(self, output: Any) -> bool:
        """Convenience method returning boolean validity."""
        return self.validate(output).is_valid


__all__ = [
    "OutputValidator",
    "OutputValidationResult",
    "ValidationResult",
    "DEFAULT_MAX_OUTPUT_LENGTH",
    "MIN_OUTPUT_LENGTH",
]
