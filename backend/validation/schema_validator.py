"""
CHAI Schema Validator.

Validates arbitrary data payloads against defined Pydantic schema models.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple, Type
from pydantic import BaseModel, ValidationError


class SchemaValidator:
    """Validates arbitrary payloads against Pydantic schema models."""

    @staticmethod
    def validate_payload(schema_cls: Type[BaseModel], payload: Any) -> Tuple[bool, Optional[BaseModel], List[str]]:
        """Validate payload against a Pydantic model class.

        Returns (is_valid, instance, errors).
        """
        try:
            if isinstance(payload, schema_cls):
                return True, payload, []
            if isinstance(payload, dict):
                inst = schema_cls(**payload)
                return True, inst, []
            return False, None, [f"Payload must be dict or {schema_cls.__name__}, got {type(payload).__name__}."]
        except ValidationError as exc:
            return False, None, [f"{err['loc']}: {err['msg']}" for err in exc.errors()]
        except Exception as exc:
            return False, None, [str(exc)]
