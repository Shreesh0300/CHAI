import json
import re
from typing import Optional, Any, Union
from langchain_core.messages import SystemMessage, HumanMessage

from backend.agents.researcher.models import ResearchResult
from backend.agents.strategist.models import (
    StrategyInput,
    StrategyResult,
)
from backend.agents.strategist.prompts import (
    SYSTEM_PROMPT,
    build_strategy_prompt,
)
from backend.shared.llm_client import (
    get_gemini_chat_model,
    get_gemini_api_key,
    get_default_gemini_model,
)
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class StrategistAgent:
    """
    Strategist Agent for CHAI multi-agent platform.
    Consumes structured ResearchResult from the Researcher Agent to define
    priorities, practical strategy, phased roadmap, trade-offs, and success metrics.
    Does not perform deep research or write technical implementation code.
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

    async def run(
        self,
        problem: str,
        research: Optional[Union[ResearchResult, dict]] = None,
        context: Optional[Union[str, dict]] = None,
    ) -> StrategyResult:
        """
        Executes the strategy synthesis workflow grounded in ResearchResult.

        Args:
            problem: Mandatory problem statement.
            research: Mandatory ResearchResult (or dict convertible to ResearchResult).
            context: Optional domain or environmental context.

        Returns:
            StrategyResult with practical strategy and roadmap or status='failed'.
        """
        # If research is not passed directly, attempt to pull it from context dict
        if research is None and isinstance(context, dict):
            research = context.get("researcher_output") or context.get("research")

        # 1. Validate ResearchResult presence and structure
        if research is None:
            logger.error("Missing ResearchResult: StrategistAgent requires structured research input.")
            raise ValueError("ResearchResult is required for StrategistAgent.")

        parsed_research: ResearchResult
        if isinstance(research, ResearchResult):
            parsed_research = research
        elif isinstance(research, dict):
            try:
                parsed_research = ResearchResult.model_validate(research)
            except Exception as e:
                logger.error(f"Invalid ResearchResult dictionary: {e}")
                raise ValueError(f"Invalid ResearchResult provided: {e}")
        else:
            raise ValueError(f"Invalid research type: expected ResearchResult or dict, got {type(research)}")

        # 2. Input validation: problem must be non-empty
        try:
            StrategyInput(
                problem=problem,
                research=parsed_research,
                context=context,
            )
        except Exception as e:
            logger.error(f"Input validation failed for StrategistAgent: {e}")
            raise ValueError(f"Input validation failed: {e}")

        # 3. Obtain LLM client
        llm = self._get_llm()
        if llm is None:
            logger.error("GEMINI_API_KEY is missing or invalid. Unable to invoke Gemini model.")
            return StrategyResult(
                agent="strategist",
                status="failed",
                strategy="",
                priorities=[],
                roadmap=[],
                tradeoffs=[],
                success_metrics=[],
            )

        # 4. Build prompt messages using ResearchResult
        user_prompt = build_strategy_prompt(
            problem=problem,
            research=parsed_research,
            context=context,
        )
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        # 5. Invoke LLM with structured output or fallback
        try:
            result = None
            if hasattr(llm, "with_structured_output"):
                try:
                    structured_llm = llm.with_structured_output(StrategyResult)
                    result = await structured_llm.ainvoke(messages)
                except Exception as struct_err:
                    logger.warning(f"with_structured_output failed ({struct_err}), falling back to direct invocation.")
                    result = await llm.ainvoke(messages)
            else:
                result = await llm.ainvoke(messages)

            # 6. Parse and validate response
            return self._parse_llm_response(result)

        except Exception as e:
            logger.error(f"Gemini API or invocation failure during strategy formulation: {e}")
            return StrategyResult(
                agent="strategist",
                status="failed",
                strategy="",
                priorities=[],
                roadmap=[],
                tradeoffs=[],
                success_metrics=[],
            )

    def _parse_llm_response(self, result: Any) -> StrategyResult:
        """Parses model response into a validated StrategyResult."""
        try:
            # Direct Pydantic instance
            if isinstance(result, StrategyResult):
                result_data = result.model_dump()
                result_data["agent"] = "strategist"
                result_data["status"] = "completed"
                return StrategyResult.model_validate(result_data)

            # Dictionary output
            if isinstance(result, dict):
                result["agent"] = "strategist"
                result["status"] = "completed"
                return StrategyResult.model_validate(result)

            # Text or AIMessage content extraction
            raw_text = getattr(result, "content", None)
            if raw_text is None:
                raw_text = str(result)

            if isinstance(raw_text, list):
                raw_text = " ".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw_text)

            json_str = self._extract_json_string(raw_text)
            parsed_json = json.loads(json_str)

            if not isinstance(parsed_json, dict):
                raise ValueError("Parsed JSON root is not an object.")

            parsed_json["agent"] = "strategist"
            parsed_json["status"] = "completed"
            return StrategyResult.model_validate(parsed_json)

        except Exception as parse_err:
            logger.error(f"Failed to parse model output into StrategyResult: {parse_err}")
            return StrategyResult(
                agent="strategist",
                status="failed",
                strategy="",
                priorities=[],
                roadmap=[],
                tradeoffs=[],
                success_metrics=[],
            )

    def _extract_json_string(self, text: str) -> str:
        """Extracts JSON substring from text or code fences."""
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()

        return text.strip()


async def strategist_node(state: dict) -> dict:
    """
    LangGraph-compatible node function.
    Reads original problem, research output, and context from state dictionary.
    Returns dictionary with StrategyResult in 'strategy_result'.
    """
    agent = StrategistAgent()
    problem = state.get("problem", "")
    research_data = state.get("research") or state.get("research_result")
    context = state.get("context")

    parsed_research = None
    if isinstance(research_data, ResearchResult):
        parsed_research = research_data
    elif isinstance(research_data, dict):
        try:
            parsed_research = ResearchResult.model_validate(research_data)
        except Exception:
            parsed_research = None

    if not parsed_research or not problem:
        return {
            "strategy_result": StrategyResult(
                agent="strategist",
                status="failed",
                strategy="",
                priorities=[],
                roadmap=[],
                tradeoffs=[],
                success_metrics=[],
            ).model_dump()
        }

    result = await agent.run(
        problem=problem,
        research=parsed_research,
        context=context,
    )
    return {"strategy_result": result.model_dump()}
