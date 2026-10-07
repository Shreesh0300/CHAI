import os
import json
import re
from typing import Optional, List, Any, Union
from langchain_core.messages import SystemMessage, HumanMessage

from backend.agents.researcher.models import (
    ResearchInput,
    ResearchResult,
    Source,
)
from backend.agents.researcher.prompts import (
    SYSTEM_PROMPT,
    build_research_prompt,
)
from backend.shared.llm_client import (
    get_gemini_chat_model,
    get_gemini_api_key,
    get_default_gemini_model,
)
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class ResearcherAgent:
    """
    Researcher Agent for CHAI multi-agent platform.
    Specializes in deeply understanding the problem requirements, stakeholders,
    constraints, assumptions, and open questions without designing downstream solutions.
    """

    def __init__(self, llm: Optional[Any] = None, model_name: Optional[str] = None):
        self.model_name = model_name or get_default_gemini_model()
        self._llm = llm

    def _get_llm(self):
        """Lazily initializes the LangChain Gemini chat model if not provided."""
        if self._llm is not None:
            return self._llm

        api_key = get_gemini_api_key()
        if not api_key:
            return None

        try:
            self._llm = get_gemini_chat_model(model_name=self.model_name, api_key=api_key)
            return self._llm
        except Exception as e:
            logger.error(f"Failed to initialize Gemini LLM client: {e}")
            return None

    def _make_mock_output(self, problem: str, sources: List[Source]) -> ResearchResult:
        """Returns a plausible mock ResearchResult when mock mode is enabled."""
        return ResearchResult(
            agent="researcher",
            status="completed",
            key_findings=[f"[Mock] Core research findings for: {problem}"],
            user_needs=["[Mock] Low-bandwidth accessibility", "[Mock] Reliable user experience"],
            constraints=["[Mock] Unreliable connectivity", "[Mock] Limited device capabilities"],
            assumptions=["[Mock] Mock mode active: no live LLM configured."],
            open_questions=["[Mock] Target operational scope and language support."],
            sources=sources,
        )

    async def run(
        self,
        problem: str,
        context: Optional[str] = None,
        acquired_information: Optional[List[Any]] = None,
        sources: Optional[List[Union[Source, dict]]] = None,
    ) -> ResearchResult:
        """
        Executes the problem analysis workflow.

        Args:
            problem: Mandatory problem statement.
            context: Optional background or domain details.
            acquired_information: Optional pre-acquired evidence.
            sources: Optional verified provenance sources.

        Returns:
            ResearchResult Pydantic model with structured findings or status='failed'.
        """
        # 1. Parse and validate sources provenance
        parsed_sources: List[Source] = []
        if sources:
            for s in sources:
                if isinstance(s, Source):
                    parsed_sources.append(s)
                elif isinstance(s, dict):
                    try:
                        parsed_sources.append(Source.model_validate(s))
                    except Exception as e:
                        logger.warning(f"Failed to validate source item: {e}")

        # 2. Input validation: fail immediately before calling Gemini if problem is empty
        try:
            ResearchInput(
                problem=problem,
                context=context,
                acquired_information=acquired_information or [],
                sources=parsed_sources,
            )
        except Exception as e:
            logger.error(f"Input validation failed for ResearcherAgent: {e}")
            raise ValueError(f"Input validation failed: {e}")

        # Check explicit mock mode
        if os.getenv("CHAI_MOCK_MODE", "").lower() in ("true", "1", "yes"):
            logger.info("ResearcherAgent: running in mock mode.")
            return self._make_mock_output(problem, parsed_sources)

        # 3. Obtain LLM client
        llm = self._get_llm()
        if llm is None:
            logger.error("GEMINI_API_KEY is missing or invalid. Unable to invoke Gemini model.")
            return ResearchResult(
                agent="researcher",
                status="failed",
                key_findings=[],
                user_needs=[],
                constraints=[],
                assumptions=[],
                open_questions=[],
                sources=[],
            )

        # 4. Build prompt messages
        user_prompt = build_research_prompt(
            problem=problem,
            context=context,
            acquired_information=acquired_information,
            sources=parsed_sources,
        )
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        # 5. Call LLM with structured output or fallback parsing
        try:
            result = None
            if hasattr(llm, "with_structured_output"):
                try:
                    structured_llm = llm.with_structured_output(ResearchResult)
                    result = await structured_llm.ainvoke(messages)
                except Exception as struct_err:
                    logger.warning(f"with_structured_output failed ({struct_err}), falling back to direct invocation.")
                    result = await llm.ainvoke(messages)
            else:
                result = await llm.ainvoke(messages)

            # 6. Parse and validate model output
            return self._parse_llm_response(result, parsed_sources)

        except Exception as e:
            logger.error(f"Gemini API or invocation failure during research: {e}")
            return ResearchResult(
                agent="researcher",
                status="failed",
                key_findings=[],
                user_needs=[],
                constraints=[],
                assumptions=[],
                open_questions=[],
                sources=[],
            )

    def _parse_llm_response(self, result: Any, initial_sources: List[Source]) -> ResearchResult:
        """Parses various LangChain response formats into a validated ResearchResult."""
        try:
            # Direct Pydantic instance from with_structured_output
            if isinstance(result, ResearchResult):
                result_data = result.model_dump()
                # Ensure agent and status are valid
                result_data["agent"] = "researcher"
                result_data["status"] = "completed"
                # Preserve verified input sources if none returned or external weren't provided
                if not result_data.get("sources") and initial_sources:
                    result_data["sources"] = initial_sources
                elif not initial_sources:
                    result_data["sources"] = []
                return ResearchResult.model_validate(result_data)

            # Dictionary output
            if isinstance(result, dict):
                result["agent"] = "researcher"
                result["status"] = "completed"
                if not result.get("sources") and initial_sources:
                    result["sources"] = initial_sources
                elif not initial_sources:
                    result["sources"] = []
                return ResearchResult.model_validate(result)

            # Text or AIMessage content extraction
            raw_text = getattr(result, "content", None)
            if raw_text is None:
                raw_text = str(result)

            if isinstance(raw_text, list):
                # Langchain multi-part content
                raw_text = " ".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw_text)

            # Extract JSON block
            json_str = self._extract_json_string(raw_text)
            parsed_json = json.loads(json_str)

            if not isinstance(parsed_json, dict):
                raise ValueError("Parsed JSON root is not an object.")

            parsed_json["agent"] = "researcher"
            parsed_json["status"] = "completed"
            if not parsed_json.get("sources") and initial_sources:
                parsed_json["sources"] = initial_sources
            elif not initial_sources:
                parsed_json["sources"] = []

            return ResearchResult.model_validate(parsed_json)

        except Exception as parse_err:
            logger.error(f"Failed to parse and validate model output into ResearchResult: {parse_err}")
            return ResearchResult(
                agent="researcher",
                status="failed",
                key_findings=[],
                user_needs=[],
                constraints=[],
                assumptions=[],
                open_questions=[],
                sources=[],
            )

    def _extract_json_string(self, text: str) -> str:
        """Extracts JSON substring from text or markdown code fences."""
        # Match ```json ... ```
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()

        # Match first { to last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()

        return text.strip()


async def researcher_node(state: dict) -> dict:
    """
    LangGraph-ready node function.
    Reads state dictionary and returns updated state with research result.
    """
    agent = ResearcherAgent()
    problem = state.get("problem", "")
    context = state.get("context")
    acquired_info = state.get("acquired_information")
    sources = state.get("sources")

    result = await agent.run(
        problem=problem,
        context=context,
        acquired_information=acquired_info,
        sources=sources,
    )
    return {"research": result.model_dump()}
