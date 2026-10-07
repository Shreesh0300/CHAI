import json
import re
from typing import Optional, Any, Union
from langchain_core.messages import SystemMessage, HumanMessage

from backend.agents.researcher.models import ResearchResult
from backend.agents.strategist.models import StrategyResult
from backend.agents.security.models import (
    SecurityInput,
    SecurityResult,
)
from backend.agents.security.prompts import (
    SYSTEM_PROMPT,
    build_security_prompt,
)
from backend.shared.llm_client import (
    get_gemini_chat_model,
    get_gemini_api_key,
    get_default_gemini_model,
)
from backend.shared.logger import get_logger

logger = get_logger(__name__)


class SecurityAgent:
    """
    Security Agent for the CHAI multi-agent platform.
    Specializes in evaluating technical security threats, attack surfaces, authentication/authorization,
    data privacy, prompt injection, and secret exposure, proposing prioritized technical mitigations.
    Distinct from the Guardian Agent which focuses on broader ethical and societal safety.
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
            logger.error(f"Failed to initialize Gemini LLM client in SecurityAgent: {e}")
            return None

    async def run(
        self,
        problem: str,
        context: Optional[Union[str, dict]] = None,
        research: Optional[Union[ResearchResult, dict]] = None,
        strategy: Optional[Union[StrategyResult, dict]] = None,
        engineering: Optional[Any] = None,
    ) -> SecurityResult:
        """
        Executes the technical security review workflow.
        Can run with problem alone, or with any available combination of upstream artifacts.

        Args:
            problem: Mandatory problem statement.
            context: Optional domain or environmental details.
            research: Optional ResearchResult from the Researcher Agent.
            strategy: Optional StrategyResult from the Strategist Agent.
            engineering: Optional engineering design specifications.

        Returns:
            SecurityResult with technical security findings or status='failed'.
        """
        # If context is passed as a dict, pull any embedded upstream outputs if not explicitly passed
        if isinstance(context, dict):
            if engineering is None:
                engineering = context.get("engineer") or context.get("engineering")
            if research is None:
                research = context.get("researcher") or context.get("research")
            if strategy is None:
                strategy = context.get("strategist") or context.get("strategy")

        # 1. Parse optional upstream models if provided as dicts
        parsed_research: Optional[ResearchResult] = None
        if research is not None:
            if isinstance(research, ResearchResult):
                parsed_research = research
            elif isinstance(research, dict):
                try:
                    parsed_research = ResearchResult.model_validate(research)
                except Exception as e:
                    logger.warning(f"Failed to parse research dict into ResearchResult: {e}")

        parsed_strategy: Optional[StrategyResult] = None
        if strategy is not None:
            if isinstance(strategy, StrategyResult):
                parsed_strategy = strategy
            elif isinstance(strategy, dict):
                try:
                    parsed_strategy = StrategyResult.model_validate(strategy)
                except Exception as e:
                    logger.warning(f"Failed to parse strategy dict into StrategyResult: {e}")

        # 2. Input validation
        try:
            SecurityInput(
                problem=problem,
                context=context,
                research=parsed_research,
                strategy=parsed_strategy,
                engineering=engineering,
            )
        except Exception as e:
            logger.error(f"Input validation failed for SecurityAgent: {e}")
            raise ValueError(f"Input validation failed: {e}")

        # 3. Obtain LLM client
        llm = self._get_llm()
        if llm is None:
            logger.error("GEMINI_API_KEY is missing or invalid. Unable to invoke Gemini model.")
            return SecurityResult(
                agent="security",
                status="failed",
            )

        # 4. Build prompt messages
        user_prompt = build_security_prompt(
            problem=problem,
            context=context,
            research=parsed_research,
            strategy=parsed_strategy,
            engineering=engineering,
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
                    structured_llm = llm.with_structured_output(SecurityResult)
                    result = await structured_llm.ainvoke(messages)
                except Exception as struct_err:
                    logger.warning(f"with_structured_output failed ({struct_err}), falling back to direct invocation.")
                    result = await llm.ainvoke(messages)
            else:
                result = await llm.ainvoke(messages)

            # 6. Parse and validate response
            return self._parse_llm_response(result)

        except Exception as e:
            logger.error(f"Gemini API or invocation failure during security review: {e}")
            return SecurityResult(
                agent="security",
                status="failed",
            )

    def _parse_llm_response(self, result: Any) -> SecurityResult:
        """Parses model response into a validated SecurityResult."""
        try:
            # Direct Pydantic instance
            if isinstance(result, SecurityResult):
                result_data = result.model_dump()
                result_data["agent"] = "security"
                result_data["status"] = "completed"
                return SecurityResult.model_validate(result_data)

            # Dictionary output
            if isinstance(result, dict):
                result["agent"] = "security"
                result["status"] = "completed"
                return SecurityResult.model_validate(result)

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

            parsed_json["agent"] = "security"
            parsed_json["status"] = "completed"
            return SecurityResult.model_validate(parsed_json)

        except Exception as parse_err:
            logger.error(f"Failed to parse model output into SecurityResult: {parse_err}")
            return SecurityResult(
                agent="security",
                status="failed",
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


async def security_node(state: dict) -> dict:
    """
    LangGraph-compatible node function.
    Reads problem, upstream research, strategy, and engineering specifications from state dictionary.
    Returns dictionary with SecurityResult in 'security_result'.
    """
    agent = SecurityAgent()
    problem = state.get("problem", "")
    research_data = state.get("research") or state.get("research_result")
    strategy_data = state.get("strategy") or state.get("strategy_result")
    engineering_data = state.get("engineering") or state.get("engineer_result")
    context = state.get("context")

    if not problem:
        return {
            "security_result": SecurityResult(
                agent="security",
                status="failed",
            ).model_dump()
        }

    result = await agent.run(
        problem=problem,
        context=context,
        research=research_data,
        strategy=strategy_data,
        engineering=engineering_data,
    )
    return {"security_result": result.model_dump()}
