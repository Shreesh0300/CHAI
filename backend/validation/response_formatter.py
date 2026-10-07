"""
CHAI Response Formatter.

Responsible for packaging, formatting, and presentation of validated deliverables.

Separation of Concerns:
- OutputValidator: Is this output safe/valid?
- ResponseFormatter: How should the valid response be packaged?
- Coordinator: How should workflow state and gate actions control delivery?
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FormattedResponse(BaseModel):
    """Structured formatted response model."""
    content: str = Field(..., description="Main delivery content.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Delivery metadata.")
    limitations: List[str] = Field(default_factory=list, description="Attached limitations.")


class ResponseFormatter:
    """Formats and packages validated CHAI final answers."""

    def format(
        self,
        text: str,
        limitations: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FormattedResponse:
        """Package text and limitations into a structured deliverable."""
        clean_text = (text or "").strip()
        clean_limitations = [str(l).strip() for l in (limitations or []) if str(l).strip()]
        return FormattedResponse(
            content=clean_text,
            metadata=metadata or {},
            limitations=clean_limitations,
        )
