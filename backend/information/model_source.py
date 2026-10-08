"""
Model Knowledge Acquisition Source for CHAI.

Leverages the shared Gemini client to acquire domain background knowledge and
theoretical concepts, returning a strictly structured ModelKnowledgeResponse and
normalizing into InformationItem objects with source_type='model' and verified=False.
"""
from __future__ import annotations

import os
import json
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from backend.information.source import BaseInformationSource, SOURCE_TYPE_MODEL
from backend.information.models import InformationItem
from backend.shared.llm_client import (
    llm_client,
    get_gemini_api_key,
    get_default_gemini_model,
)
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class ModelKnowledgeResponse(BaseModel):
    """
    Structured response contract for model-generated knowledge retrieval.
    Enforces structured decomposition rather than raw unstructured prose.
    """
    knowledge: List[str] = Field(
        default_factory=list,
        description="Factual domain concepts, principles, and recognized patterns"
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Underlying assumptions embedded in this model analysis"
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Boundaries, gaps, and potential training cutoff limitations"
    )
    suggested_areas_to_verify: List[str] = Field(
        default_factory=list,
        description="Key claims or data points requiring external empirical verification"
    )


class ModelKnowledgeSource(BaseInformationSource):
    """
    Information source that queries the shared Gemini LLM for domain background knowledge.
    Explicitly flags all retrieved items as unverified model knowledge (verified=False)
    so the Researcher can separate empirical evidence from generative priors.
    """
    source_type: str = SOURCE_TYPE_MODEL

    def __init__(
        self,
        model_name: Optional[str] = None,
        client: Optional[Any] = None,
    ):
        self.model_name = model_name or get_default_gemini_model()
        self.client = client or llm_client
        self.last_errors: List[str] = []

    async def acquire(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> List[InformationItem]:
        """
        Retrieves structured background knowledge from Gemini and packages it
        into normalized InformationItems with provenance indicating unverified status.
        """
        self.last_errors = []
        cleaned_query = (query or "").strip()

        if not cleaned_query:
            return []

        # Check mock mode or absent API key
        is_mock = os.getenv("CHAI_MOCK_MODE", "").lower() in ("true", "1", "yes")
        has_key = bool(get_gemini_api_key())

        if is_mock or not has_key:
            logger.info("ModelKnowledgeSource: generating deterministic model knowledge in mock/offline mode")
            mock_resp = self._create_mock_response(cleaned_query)
            return [self._to_information_item(mock_resp, cleaned_query)]

        prompt = (
            f"You are providing structured domain background knowledge for the following inquiry:\n\n"
            f"Query: {cleaned_query}\n"
            f"Context: {context or 'None provided'}\n\n"
            f"Provide a structured technical overview. Respond ONLY in valid JSON with these exact keys:\n"
            f"{{\n"
            f'  "knowledge": ["key conceptual fact 1", "key conceptual fact 2"],\n'
            f'  "assumptions": ["underlying technical assumption 1"],\n'
            f'  "limitations": ["knowledge cutoff or scope limitation"],\n'
            f'  "suggested_areas_to_verify": ["empirical point requiring verification"]\n'
            f"}}\n"
            f"Do not include conversational filler or markdown other than valid json."
        )

        system_instruction = (
            "You are a specialized knowledge-retrieval module. Provide concise, high-signal, "
            "technical domain principles in strict JSON format."
        )

        try:
            raw_text = await self.client.generate_content(
                prompt=prompt,
                system_instruction=system_instruction,
            )

            parsed_data = self._parse_json(raw_text)
            model_resp = ModelKnowledgeResponse.model_validate(parsed_data)
            return [self._to_information_item(model_resp, cleaned_query)]

        except Exception as e:
            err_msg = f"Model knowledge acquisition failed: {type(e).__name__}"
            logger.warning(f"ModelKnowledgeSource: {err_msg} ({e})")
            self.last_errors.append(err_msg)
            return []

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Safely parses JSON even if wrapped in markdown code blocks."""
        cleaned = text.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()
        return json.loads(cleaned)

    def _to_information_item(self, resp: ModelKnowledgeResponse, query: str) -> InformationItem:
        """Converts ModelKnowledgeResponse into a normalized InformationItem."""
        lines = ["Model-Generated Domain Knowledge (Unverified):"]
        for k in resp.knowledge:
            lines.append(f"- Concept: {k}")
        if resp.assumptions:
            lines.append("\nEmbedded Assumptions:")
            for a in resp.assumptions:
                lines.append(f"- {a}")
        if resp.limitations:
            lines.append("\nKnown Model Limitations:")
            for l in resp.limitations:
                lines.append(f"- {l}")
        if resp.suggested_areas_to_verify:
            lines.append("\nRecommended Verification Areas:")
            for v in resp.suggested_areas_to_verify:
                lines.append(f"- {v}")

        content_text = "\n".join(lines)
        label_title = f"Model Knowledge: {query[:50]}" if len(query) > 50 else f"Model Knowledge: {query}"

        return InformationItem(
            content=content_text,
            title=label_title,
            url=None,
            source=self.model_name,
            source_type=SOURCE_TYPE_MODEL,
            metadata={
                "provider": "gemini",
                "model": self.model_name,
                "verified": False,
                "source_category": "model_knowledge",
                "query": query,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "assumptions": resp.assumptions,
                "limitations": resp.limitations,
                "suggested_areas_to_verify": resp.suggested_areas_to_verify,
            },
        )

    def _create_mock_response(self, query: str) -> ModelKnowledgeResponse:
        """Deterministic fallback response for offline testing."""
        return ModelKnowledgeResponse(
            knowledge=[
                f"Core architectural foundation for '{query}': High-availability distributed principles.",
                "Established standard: Zero-trust network segmentation and defense-in-depth.",
            ],
            assumptions=[
                "Standard POSIX/Cloud-native hosting environment assumed.",
            ],
            limitations=[
                "Model-generated heuristic; pending live external empirical validation.",
            ],
            suggested_areas_to_verify=[
                "Verify latency tolerances under peak transaction volume.",
                "Verify compatibility with regional compliance regimes.",
            ],
        )


__all__ = ["ModelKnowledgeSource", "ModelKnowledgeResponse"]
