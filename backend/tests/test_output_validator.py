"""
Comprehensive test suite for CHAI Output Validator.

Validates:
1. Basic Validation:
   - Valid normal response
   - Empty response
   - Whitespace-only response
   - Wrong input types (None, dict, int)
   - Null-byte detection
   - Length bounds & boundary values
2. Traceback & Internal Error Detection:
   - Python traceback detection
   - Internal file path stack trace detection
   - Normal code containing 'Exception' passes
   - Educational try-except code blocks pass
3. Secret & Credential Leak Detection:
   - Google API key (AIzaSy...)
   - OpenAI API key (sk-...)
   - GitHub tokens (ghp_...)
   - AWS access keys (AKIA...)
   - Private key blocks (-----BEGIN PRIVATE KEY-----)
   - Real JWT bearer tokens
   - Hardcoded high-entropy secret assignments
4. False-Positive Protections:
   - Mentions of 'password', 'token', 'secret', 'API key'
   - Placeholder tokens (Bearer <token>, YOUR_TOKEN)
   - Django SECRET_KEY documentation
5. Normal Content & Edge Cases:
   - Markdown structure, headings, lists
   - Multiline code blocks
   - Markdown tables
   - Unicode & non-ASCII text
   - JSON snippets
   - Unclosed fence non-blocking warning
6. Raw Object Representation Detection:
   - Python object dump detection (<... object at 0x...>)
7. Reliability Monitor & Coordinator Integration:
   - PROCEED flow
   - PROCEED_WITH_LIMITATIONS flow & limitation preservation
   - REQUEST_MORE_INFORMATION flow & clarification delivery
   - BLOCK_OUTPUT flow & safe blocked message delivery
   - Blocked synthesized answer isolation
8. Output Validator Failure Handling:
   - Internal exception safe degradation
   - Blocked delivery on validation failure in Coordinator
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from backend.validation.output_validator import (
    OutputValidator,
    OutputValidationResult,
    DEFAULT_MAX_OUTPUT_LENGTH,
    MIN_OUTPUT_LENGTH,
)
from backend.validation.response_formatter import ResponseFormatter, FormattedResponse
from backend.validation.schema_validator import SchemaValidator
from backend.core.coordinator import Coordinator
from backend.core.schemas import SolveRequest
from backend.agents.reliability_monitor.schemas import (
    AgentStatus,
    ReliabilityLevel,
    ReliabilityAction,
    ReliabilityMonitorResult,
)


# ==============================================================================
# 1. Basic Structural Validation Tests
# ==============================================================================

def test_valid_normal_response():
    """1. Test that normal, well-formed responses pass validation."""
    validator = OutputValidator()
    result = validator.validate("This is a valid technical answer explaining Python list slicing.")
    assert result.is_valid is True
    assert result.valid is True
    assert len(result.errors) == 0
    assert len(result.issues) == 0
    assert result.sanitized_output == "This is a valid technical answer explaining Python list slicing."


def test_empty_response():
    """2. Test that completely empty responses fail validation."""
    validator = OutputValidator()
    result = validator.validate("")
    assert result.is_valid is False
    assert result.valid is False
    assert any("empty" in e.lower() for e in result.errors)


def test_whitespace_only_response():
    """3. Test that whitespace-only responses fail validation."""
    validator = OutputValidator()
    result = validator.validate("   \n\t   \r\n   ")
    assert result.is_valid is False
    assert any("empty" in e.lower() or "whitespace" in e.lower() for e in result.errors)


def test_wrong_input_type_none():
    """4. Test that None input fails validation without throwing an uncaught exception."""
    validator = OutputValidator()
    result = validator.validate(None)
    assert result.is_valid is False
    assert any("none" in e.lower() for e in result.errors)


def test_wrong_input_type_dict_and_int():
    """4b. Test that non-string inputs fail validation gracefully."""
    validator = OutputValidator()
    res_dict = validator.validate({"answer": "hello"})
    assert res_dict.is_valid is False
    assert any("string" in e.lower() for e in res_dict.errors)

    res_int = validator.validate(42)
    assert res_int.is_valid is False
    assert any("string" in e.lower() for e in res_int.errors)


def test_null_byte_detection():
    """5. Test that responses with corrupted null bytes are rejected."""
    validator = OutputValidator()
    result = validator.validate("Valid prefix text \x00 corrupted null byte payload")
    assert result.is_valid is False
    assert any("null byte" in e.lower() for e in result.errors)


def test_response_too_long():
    """6. Test that responses exceeding maximum length threshold are rejected."""
    validator = OutputValidator(max_length=100)
    oversized = "a" * 101
    result = validator.validate(oversized)
    assert result.is_valid is False
    assert any("exceeds maximum" in e.lower() for e in result.errors)


def test_response_at_valid_maximum_boundary():
    """7. Test that responses exactly at maximum length pass validation."""
    validator = OutputValidator(max_length=100)
    boundary_text = "a" * 100
    result = validator.validate(boundary_text)
    assert result.is_valid is True
    assert result.sanitized_output == boundary_text


# ==============================================================================
# 2. Traceback & Internal Error Detection Tests
# ==============================================================================

def test_traceback_detection():
    """8. Test that accidental Python traceback dumps are caught and blocked."""
    validator = OutputValidator()
    text = (
        "Here is the result:\n"
        "Traceback (most recent call last):\n"
        "  File 'app.py', line 12, in <module>\n"
        "ZeroDivisionError: division by zero"
    )
    result = validator.validate(text)
    assert result.is_valid is False
    assert any("traceback" in e.lower() or "stack trace" in e.lower() for e in result.errors)


def test_raw_internal_file_stack_trace_detection():
    """9. Test that internal backend stack traces are detected."""
    validator = OutputValidator()
    text = 'An internal failure occurred:\nFile "backend/core/coordinator.py", line 142, in process_request\nValueError: invalid input'
    result = validator.validate(text)
    assert result.is_valid is False
    assert any("stack trace" in e.lower() or "traceback" in e.lower() for e in result.errors)


def test_normal_code_containing_exception_passes():
    """10. Test that normal educational code mentioning Exception passes validation."""
    validator = OutputValidator()
    text = (
        "In Python, handle errors using try/except blocks:\n"
        "```python\n"
        "try:\n"
        "    result = calculate()\n"
        "except Exception as e:\n"
        "    logger.error(f'Calculation failed: {e}')\n"
        "```\n"
        "This ensures clean error handling without unhandled crashes."
    )
    result = validator.validate(text)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_educational_try_except_code_block_passes():
    """11. Test that explaining common errors does not trigger false positives."""
    validator = OutputValidator()
    text = (
        "When an invalid index is accessed, Python raises an IndexError. "
        "You can catch it specifically:\n"
        "```python\n"
        "try:\n"
        "    item = my_list[10]\n"
        "except IndexError:\n"
        "    item = None\n"
        "```"
    )
    result = validator.validate(text)
    assert result.is_valid is True
    assert len(result.errors) == 0


# ==============================================================================
# 3. Secret & Credential Leak Detection Tests
# ==============================================================================

def test_google_api_key_detected():
    """12. Test that real Google API key formats are detected and blocked."""
    validator = OutputValidator()
    leaked = "API config: AIzaSyA1234567890123456789012345678901"
    result = validator.validate(leaked)
    assert result.is_valid is False
    assert any("credential" in e.lower() or "security pattern" in e.lower() for e in result.errors)


def test_openai_api_key_detected():
    """13. Test that real OpenAI API keys are detected."""
    validator = OutputValidator()
    leaked = "client = OpenAI(api_key='sk-proj-abc123def456ghi789jkl012mno345pqr678')"
    result = validator.validate(leaked)
    assert result.is_valid is False
    assert any("credential" in e.lower() or "security pattern" in e.lower() for e in result.errors)


def test_github_token_detected():
    """14. Test that GitHub personal access tokens are detected."""
    validator = OutputValidator()
    leaked = "export GITHUB_TOKEN=ghp_123456789012345678901234567890123456"
    result = validator.validate(leaked)
    assert result.is_valid is False
    assert any("credential" in e.lower() or "security pattern" in e.lower() for e in result.errors)


def test_aws_access_key_detected():
    """15. Test that AWS Access Key IDs are detected."""
    validator = OutputValidator()
    leaked = "AWS credentials found: AKIAIOSFODNN7EXAMPLE"
    result = validator.validate(leaked)
    assert result.is_valid is False
    assert any("credential" in e.lower() or "security pattern" in e.lower() for e in result.errors)


def test_private_key_detected():
    """16. Test that PEM private key blocks are detected."""
    validator = OutputValidator()
    leaked = (
        "Server certificate key:\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Yq4...\n"
        "-----END RSA PRIVATE KEY-----"
    )
    result = validator.validate(leaked)
    assert result.is_valid is False
    assert any("private key" in e.lower() or "credential" in e.lower() for e in result.errors)


def test_jwt_bearer_token_detected():
    """17. Test that real JWT bearer tokens are detected."""
    validator = OutputValidator()
    # Real JWT format header.payload.signature
    jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    leaked = f"Authorization: Bearer {jwt_token}"
    result = validator.validate(leaked)
    assert result.is_valid is False
    assert any("credential" in e.lower() or "security pattern" in e.lower() for e in result.errors)


def test_hardcoded_secret_assignment_detected():
    """18. Test that hardcoded secret assignments with long strings are caught."""
    validator = OutputValidator()
    leaked = 'api_key = "a8f7c9e1b2d3f4e5a6b7c8d9e0f1a2b3"'
    result = validator.validate(leaked)
    assert result.is_valid is False
    assert any("credential" in e.lower() or "security pattern" in e.lower() for e in result.errors)


# ==============================================================================
# 4. False-Positive Protections Tests
# ==============================================================================

def test_educational_password_mention_passes():
    """19. Test that mentioning 'password' in ordinary educational content passes."""
    validator = OutputValidator()
    text = "This example uses a password variable to illustrate user hashing with bcrypt."
    result = validator.validate(text)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_educational_api_key_advice_passes():
    """20. Test that discussing API key best practices passes."""
    validator = OutputValidator()
    text = "Never expose your API key in clientside code. Store it in environment variables or a secrets manager."
    result = validator.validate(text)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_educational_token_mention_passes():
    """21. Test that mentioning authentication tokens passes."""
    validator = OutputValidator()
    text = "Authentication tokens should be stored securely in HTTP-only cookies to mitigate XSS attacks."
    result = validator.validate(text)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_educational_exception_handler_passes():
    """22. Test that explaining exception handlers passes."""
    validator = OutputValidator()
    text = "Here is an example exception handler for database reconnection backoff."
    result = validator.validate(text)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_toy_code_password_assignment_passes():
    """23. Test that simple short toy passwords in tutorials do not fail."""
    validator = OutputValidator()
    text = (
        "In your unit tests, you can use a fixture user:\n"
        "```python\n"
        "test_user = {'username': 'alice', 'password': 'test_password'}\n"
        "```"
    )
    result = validator.validate(text)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_authorization_bearer_placeholder_passes():
    """24. Test that placeholder bearer token documentation passes."""
    validator = OutputValidator()
    text = "Send your requests with the header: `Authorization: Bearer <your-access-token>`."
    result = validator.validate(text)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_django_secret_key_doc_passes():
    """25. Test that referencing Django SECRET_KEY in documentation passes."""
    validator = OutputValidator()
    text = "In production, ensure Django SECRET_KEY is loaded from environment variables rather than hardcoded in settings.py."
    result = validator.validate(text)
    assert result.is_valid is True
    assert len(result.errors) == 0


# ==============================================================================
# 5. Normal Content & Edge Cases Tests
# ==============================================================================

def test_markdown_formatting_passes():
    """26. Test that standard markdown structures validate cleanly."""
    validator = OutputValidator()
    text = (
        "# System Architecture Plan\n\n"
        "## Components\n"
        "- **Gateway**: Reverse proxy with TLS termination\n"
        "- **Application**: FastAPI microservices\n"
        "- **Database**: PostgreSQL with read replicas\n\n"
        "> Note: Ensure database backups are taken nightly."
    )
    result = validator.validate(text)
    assert result.is_valid is True
    assert result.sanitized_output == text


def test_multiline_code_blocks_pass():
    """27. Test that valid multiline code blocks in various languages pass."""
    validator = OutputValidator()
    text = (
        "Here is the implementation of binary search in Python:\n\n"
        "```python\n"
        "def binary_search(arr, target):\n"
        "    low, high = 0, len(arr) - 1\n"
        "    while low <= high:\n"
        "        mid = (low + high) // 2\n"
        "        if arr[mid] == target:\n"
        "            return mid\n"
        "        elif arr[mid] < target:\n"
        "            low = mid + 1\n"
        "        else:\n"
        "            high = mid - 1\n"
        "    return -1\n"
        "```"
    )
    result = validator.validate(text)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_markdown_tables_pass():
    """28. Test that Markdown tables pass validation."""
    validator = OutputValidator()
    text = (
        "| Feature | PostgreSQL | Cassandra |\n"
        "|---|---|---|\n"
        "| ACID | Full | Tunable |\n"
        "| Sharding | Citus | Native |\n"
        "| Query | SQL | CQL |\n"
    )
    result = validator.validate(text)
    assert result.is_valid is True


def test_unicode_and_non_ascii_passes():
    """29. Test that Unicode and international characters pass validation."""
    validator = OutputValidator()
    text = "Hier ist die Architekturlösung mit deutschen Umlauten: Ä, Ö, Ü, ß. 日本語のアーキテクチャ設計。"
    result = validator.validate(text)
    assert result.is_valid is True
    assert "日本語" in result.sanitized_output


def test_json_snippets_pass():
    """30. Test that valid JSON blocks pass validation."""
    validator = OutputValidator()
    text = (
        "Configuration schema:\n"
        "```json\n"
        "{\n"
        '  "host": "localhost",\n'
        '  "port": 5432,\n'
        '  "max_connections": 100\n'
        "}\n"
        "```"
    )
    result = validator.validate(text)
    assert result.is_valid is True


def test_valid_urls_pass():
    """31. Test that documentation with URLs passes validation."""
    validator = OutputValidator()
    text = "Refer to the official documentation at https://fastapi.tiangolo.com/tutorial/ for detailed guides."
    result = validator.validate(text)
    assert result.is_valid is True


def test_unclosed_code_fence_emits_warning_not_failure():
    """32. Test that unclosed code fence produces a non-blocking warning."""
    validator = OutputValidator()
    text = "Here is a code snippet:\n```python\nprint('hello')\n"
    result = validator.validate(text)
    # Warning, NOT a blocking failure
    assert result.is_valid is True
    assert len(result.warnings) > 0
    assert any("unclosed" in w.lower() for w in result.warnings)


# ==============================================================================
# 6. Raw Object Representation Detection Tests
# ==============================================================================

def test_raw_object_dump_detected():
    """33. Test that accidentally dumping a raw Python object string is caught."""
    validator = OutputValidator()
    text = "Synthesizer completed: <backend.core.schemas.FinalResponse object at 0x7fa81234c90>"
    result = validator.validate(text)
    assert result.is_valid is False
    assert any("raw object dump" in e.lower() for e in result.errors)


# ==============================================================================
# 7. Reliability Monitor & Coordinator Integration Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_coordinator_proceed_passes_validator():
    """34. Test that PROCEED result passes through Output Validator to final delivery."""
    coordinator = Coordinator()
    mock_rm = ReliabilityMonitorResult(
        reliability_score=0.92,
        reliability_level=ReliabilityLevel.HIGH,
        action=ReliabilityAction.PROCEED,
    )
    coordinator.reliability_monitor.run = AsyncMock(return_value=mock_rm)
    coordinator.evaluator.run = AsyncMock(return_value={"status": "completed", "overall_assessment": "Verified plan"})

    spy_validate = MagicMock(wraps=coordinator.output_validator.validate)
    coordinator.output_validator.validate = spy_validate

    req = SolveRequest(problem="System design", selected_agents=["evaluator", "reliability_monitor"])
    resp = await coordinator.process_request(req)

    assert spy_validate.call_count == 1
    assert resp.request_status == "completed"
    assert "Verified plan" in resp.final_synthesized_answer


@pytest.mark.asyncio
async def test_coordinator_proceed_with_limitations_preserves_limitations():
    """35. Test that PROCEED_WITH_LIMITATIONS delivers answer and preserves limitations."""
    coordinator = Coordinator()
    mock_rm = ReliabilityMonitorResult(
        reliability_score=0.75,
        reliability_level=ReliabilityLevel.MEDIUM,
        action=ReliabilityAction.PROCEED_WITH_LIMITATIONS,
        limitations=["Audit compliance review recommended"],
        concerns=["Potential write bottleneck under 10k RPS"],
    )
    coordinator.reliability_monitor.run = AsyncMock(return_value=mock_rm)
    coordinator.guardian.run = AsyncMock(return_value={"status": "completed", "limitations": ["Data residency compliance required"]})

    req = SolveRequest(problem="Ledger design", selected_agents=["guardian", "reliability_monitor"])
    resp = await coordinator.process_request(req)

    assert resp.request_status == "completed"
    assert "Audit compliance review recommended" in resp.limitations
    assert "Potential write bottleneck under 10k RPS" in resp.limitations
    assert "Data residency compliance required" in resp.limitations


@pytest.mark.asyncio
async def test_coordinator_request_more_information_validates_and_delivers_clarification():
    """36. Test that REQUEST_MORE_INFORMATION delivers structured clarification, validated by Output Validator."""
    coordinator = Coordinator()
    mock_rm = ReliabilityMonitorResult(
        reliability_score=0.50,
        reliability_level=ReliabilityLevel.MEDIUM,
        action=ReliabilityAction.REQUEST_MORE_INFORMATION,
        missing_information=["Expected concurrent user count", "Target latency SLA"],
    )
    coordinator.reliability_monitor.run = AsyncMock(return_value=mock_rm)
    coordinator.engineer.run = AsyncMock(return_value={
        "status": "completed",
        "technical_architecture": "Internal candidate architecture with Redis and Kafka",
    })

    spy_validate = MagicMock(wraps=coordinator.output_validator.validate)
    coordinator.output_validator.validate = spy_validate

    req = SolveRequest(problem="High scale architecture", selected_agents=["engineer", "reliability_monitor"])
    resp = await coordinator.process_request(req)

    # Output validator was called to validate the clarification request
    assert spy_validate.call_count == 1
    # Synthesized candidate answer is NOT delivered
    assert "Internal candidate architecture with Redis and Kafka" not in resp.final_synthesized_answer
    # Missing information is clearly exposed
    assert "Expected concurrent user count" in resp.final_synthesized_answer
    assert "Target latency SLA" in resp.final_synthesized_answer
    assert resp.request_status == "requires_information"


@pytest.mark.asyncio
async def test_coordinator_block_output_validates_and_delivers_blocked_message():
    """37. Test that BLOCK_OUTPUT delivers a safe blocked message, validated by Output Validator."""
    coordinator = Coordinator()
    mock_rm = ReliabilityMonitorResult(
        reliability_score=0.25,
        reliability_level=ReliabilityLevel.LOW,
        action=ReliabilityAction.BLOCK_OUTPUT,
        concerns=["Severe patient privacy HIPAA violation"],
    )
    coordinator.reliability_monitor.run = AsyncMock(return_value=mock_rm)
    coordinator.engineer.run = AsyncMock(return_value={
        "status": "completed",
        "technical_architecture": "Store all healthcare patient records in public cloud bucket",
    })

    spy_validate = MagicMock(wraps=coordinator.output_validator.validate)
    coordinator.output_validator.validate = spy_validate

    req = SolveRequest(problem="Medical store", selected_agents=["engineer", "reliability_monitor"])
    resp = await coordinator.process_request(req)

    assert spy_validate.call_count == 1
    assert "Store all healthcare patient records in public cloud bucket" not in resp.final_synthesized_answer
    assert resp.final_synthesized_answer.startswith("[BLOCKED]")
    assert "Severe patient privacy HIPAA violation" in resp.final_synthesized_answer
    assert resp.request_status == "blocked"


# ==============================================================================
# 8. Output Validator Failure & Delivery Blocker Tests
# ==============================================================================

def test_validator_internal_exception_handled_safely():
    """38. Test that internal exceptions during validation degrade safely to failure."""
    validator = OutputValidator()
    validator._do_validate = MagicMock(side_effect=RuntimeError("Unexpected regex engine crash"))

    result = validator.validate("Candidate text")
    assert result.is_valid is False
    assert any("internal error" in e.lower() for e in result.errors)
    assert result.sanitized_output is None


@pytest.mark.asyncio
async def test_failed_validation_blocks_delivery_in_coordinator():
    """39. Test that a failed validation stops delivery and returns a safe blocked message in Coordinator."""
    coordinator = Coordinator()
    # Simulate an agent accidentally producing an answer with a leaked credential
    coordinator.evaluator.run = AsyncMock(return_value={
        "status": "completed",
        "overall_assessment": "Architecture with leak: AIzaSyA1234567890123456789012345678901",
    })

    req = SolveRequest(problem="System check", selected_agents=["evaluator"])
    resp = await coordinator.process_request(req)

    # Leaked credential MUST NOT be delivered in the final answer
    assert "AIzaSyA1234567890123456789012345678901" not in resp.final_synthesized_answer
    assert resp.final_synthesized_answer.startswith("[DELIVERY BLOCKED]")
    assert resp.request_status == "failed"
    # Output validator result is recorded in agent_outputs
    assert resp.agent_outputs["output_validator"]["is_valid"] is False


@pytest.mark.asyncio
async def test_validator_result_stored_in_agent_outputs():
    """40. Test that Output Validator result metadata is preserved in agent_outputs."""
    coordinator = Coordinator()
    coordinator.evaluator.run = AsyncMock(return_value={"status": "completed", "overall_assessment": "Healthy design"})

    req = SolveRequest(problem="Clean design", selected_agents=["evaluator"])
    resp = await coordinator.process_request(req)

    assert "output_validator" in resp.agent_outputs
    ov = resp.agent_outputs["output_validator"]
    assert ov["is_valid"] is True
    assert "length" in ov["validation_metadata"]


# ==============================================================================
# 9. Auxiliary Validation Modules Tests
# ==============================================================================

def test_response_formatter():
    """41. Test ResponseFormatter packages deliverable and limitations."""
    formatter = ResponseFormatter()
    res = formatter.format(
        text="Final unified deliverable text.",
        limitations=["Audit compliance required"],
        metadata={"version": "1.0"},
    )
    assert isinstance(res, FormattedResponse)
    assert res.content == "Final unified deliverable text."
    assert res.limitations == ["Audit compliance required"]
    assert res.metadata["version"] == "1.0"


def test_schema_validator():
    """42. Test SchemaValidator validates models correctly."""
    class SampleModel(FormattedResponse):
        pass

    is_valid, inst, errors = SchemaValidator.validate_payload(
        SampleModel,
        {"content": "sample content", "limitations": []},
    )
    assert is_valid is True
    assert inst.content == "sample content"
    assert len(errors) == 0

    is_invalid, _, errors_inv = SchemaValidator.validate_payload(
        SampleModel,
        {"wrong_field": 123},
    )
    assert is_invalid is False
    assert len(errors_inv) > 0
