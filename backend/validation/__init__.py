"""
CHAI Validation package.
Exports OutputValidator and ValidationResult.
"""
from backend.validation.output_validator import OutputValidator
from backend.core.contracts import ValidationResult

__all__ = ["OutputValidator", "ValidationResult"]
