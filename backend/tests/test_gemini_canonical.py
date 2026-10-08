"""
Deterministic unit tests for the canonical Gemini client integration,
schema transformation, error classification, and agent initialization.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel, Field

from backend.shared.llm_client import (
    GeminiClient,
    clean_gemini_schema,
    classify_gemini_error,
    get_gemini_api_key,
    get_default_gemini_model,
    sanitize_api_keys,
    llm_client,
)
from backend.agents.engineer.schemas import EngineerResult
from backend.agents.researcher.models import ResearchResult
from backend.agents.strategist.models import StrategyResult
from backend.agents.security.models import SecurityResult
from backend.agents.researcher.agent import ResearcherAgent
from backend.agents.strategist.agent import StrategistAgent
from backend.agents.security.agent import SecurityAgent
from backend.agents.engineer.agent import EngineerAgent


# ==============================================================================
# 1. Gemini Client Initialization & Configuration
# ==============================================================================

def test_gemini_client_initialization_defaults(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestKey1234567890abcdef")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    client = GeminiClient()
    assert client.api_key == "AIzaSyTestKey1234567890abcdef"
    assert client.model_name == "gemini-flash-lite-latest"


def test_gemini_client_explicit_override():
    client = GeminiClient(api_key="custom-key-xyz", model_name="custom-model-abc")
    assert client.api_key == "custom-key-xyz"
    assert client.model_name == "custom-model-abc"


def test_gemini_api_key_redaction():
    secret = "AIzaSySecretApiKey1234567890abcdef"
    raw_text = f"Error during call with key={secret} occurred"
    sanitized = sanitize_api_keys(raw_text)
    assert secret not in sanitized
    assert "[REDACTED]" in sanitized


# ==============================================================================
# 2. Schema Cleaning & Compatibility Layer
# ==============================================================================

class NestedSubModel(BaseModel):
    name: str = Field(default="test", description="Sub item name")
    count: int = Field(default=0, description="Count")

class ComplexModel(BaseModel):
    title: str = Field(description="Title of object")
    items: list[NestedSubModel] = Field(default_factory=list, description="List of items")
    status: str = Field(default="active", description="Status code")


def test_clean_gemini_schema_strips_defaults_and_inlines_defs():
    cleaned = clean_gemini_schema(ComplexModel)
    assert isinstance(cleaned, dict)
    # Check that $defs is removed / inlined
    assert "$defs" not in cleaned
    assert "definitions" not in cleaned
    # Check that 'default' keyword is completely stripped from schema
    schema_str = str(cleaned)
    assert "'default':" not in schema_str
    # Check that required properties are preserved
    assert "title" in cleaned.get("required", [])
    assert "properties" in cleaned
    assert "items" in cleaned["properties"]


def test_clean_gemini_schema_engineer_result():
    cleaned = clean_gemini_schema(EngineerResult)
    assert isinstance(cleaned, dict)
    assert "$defs" not in cleaned
    assert "'default':" not in str(cleaned)
    assert "properties" in cleaned
    assert "problem_understanding" in cleaned["properties"]


def test_clean_gemini_schema_research_strategy_security():
    for model_cls in (ResearchResult, StrategyResult, SecurityResult):
        cleaned = clean_gemini_schema(model_cls)
        assert isinstance(cleaned, dict)
        assert "$defs" not in cleaned
        assert "'default':" not in str(cleaned)


# ==============================================================================
# 3. Error Classification
# ==============================================================================

def test_classify_gemini_error_sdk_import():
    err = ImportError("No module named 'google.genai'")
    tag, msg = classify_gemini_error(err)
    assert tag == "[SDK_IMPORT_ERROR]"
    assert "missing" in msg.lower() or "google.genai" in msg


def test_classify_gemini_error_config_missing():
    err = Exception("GEMINI_API_KEY is not configured")
    tag, msg = classify_gemini_error(err)
    assert tag == "[CONFIG_ERROR]"


def test_classify_gemini_error_quota_429():
    err = Exception("429 ResourceExhausted: Quota exceeded for model")
    tag, msg = classify_gemini_error(err)
    assert tag == "[QUOTA_ERROR]"


def test_classify_gemini_error_auth_failure():
    err = Exception("401 Unauthorized: Invalid API key")
    tag, msg = classify_gemini_error(err)
    assert tag == "[AUTH_ERROR]"


def test_classify_gemini_error_timeout():
    err = asyncio.TimeoutError("Request timed out after 30s")
    tag, msg = classify_gemini_error(err)
    assert tag == "[TIMEOUT_ERROR]"


def test_classify_gemini_error_schema():
    err = Exception("Unknown field for Schema: default")
    tag, msg = classify_gemini_error(err)
    assert tag == "[SCHEMA_ERROR]"


def test_classify_gemini_error_network():
    err = Exception("ConnectionRefusedError: network failure")
    tag, msg = classify_gemini_error(err)
    assert tag == "[NETWORK_ERROR]"


# ==============================================================================
# 4. Agent Initialization with Canonical Shared Client
# ==============================================================================

def test_researcher_agent_canonical_client():
    agent = ResearcherAgent()
    assert agent._get_llm() is llm_client


def test_strategist_agent_canonical_client():
    agent = StrategistAgent()
    assert agent._get_llm() is llm_client


def test_security_agent_canonical_client():
    agent = SecurityAgent()
    assert agent._get_llm() is llm_client


def test_engineer_agent_canonical_client():
    agent = EngineerAgent()
    assert (agent.llm_client or llm_client) is llm_client


# ==============================================================================
# 5. Gemini Client Mocked Structured Call & Quota Error Propagation
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_client_generate_content_success():
    client = GeminiClient(api_key="AIzaSyTestKey123")
    mock_resp = MagicMock()
    mock_resp.text = '{"problem_understanding": "Clear", "status": "completed"}'
    
    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(return_value=mock_resp)
    client._client = MagicMock(aio=mock_aio)

    with patch.dict("os.environ", {"CHAI_MOCK_MODE": "false"}):
        result = await client.generate_content("Analyze RAG system", response_schema=EngineerResult)
        assert "problem_understanding" in result
        mock_aio.models.generate_content.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_client_generate_content_quota_error_sanitized():
    client = GeminiClient(api_key="AIzaSyTestKey123")
    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(
        side_effect=Exception("429 ResourceExhausted: rate limit exceeded for key AIzaSyTestKey123")
    )
    client._client = MagicMock(aio=mock_aio)

    with patch.dict("os.environ", {"CHAI_MOCK_MODE": "false"}):
        with pytest.raises(RuntimeError) as exc_info:
            await client.generate_content("Test query")
        err_msg = str(exc_info.value)
        assert "[QUOTA_ERROR]" in err_msg
        assert "AIzaSyTestKey123" not in err_msg
