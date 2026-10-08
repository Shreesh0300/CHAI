"""
Unit and integration tests for CHAI Conversational Layer and Memory System.
Covers:
1. Intent Router (greeting/simple -> CHAT, complex/architecture -> SOLVE)
2. Chat continuity (short-term history retention)
3. Long-term memory extraction (durable goal extracted, transient suppressed)
4. Memory retrieval (relevant retrieved, unrelated excluded)
5. User isolation (user A cannot access user B's memory/conversations)
6. Guest isolation (guest sessions remain strictly isolated)
7. Personalized solve (relevant user context reaches LangGraph SolveRequest)
8. Existing solve regression (/api/solve remains operational)
9. Chat failures (safe handling of model errors)
10. Memory failure isolation (memory extraction errors do not crash user response)
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.chat.router import IntentRouter
from backend.chat.schemas import IntentResult, ChatRequest
from backend.chat.service import LangChainChatService
from backend.memory.models import MemoryCategory, MemoryItem
from backend.memory.store import MemoryStore, memory_store, sanitize_sensitive_data, is_guest_user
from backend.memory.extraction import MemoryExtractor
from backend.memory.retrieval import MemoryRetriever
from backend.memory.context import ContextManager, context_manager
from backend.core.schemas import SolveRequest


@pytest.fixture
def app_client():
    app = create_app()
    return TestClient(app)


# =============================================================================
# 1. Intent Router Tests
# =============================================================================

@pytest.mark.asyncio
async def test_intent_router_greetings_route_to_chat():
    router = IntentRouter()
    for greeting in ["hello", "hey", "good morning", "how are you?", "what's up"]:
        res = await router.classify(greeting)
        assert res.intent == "chat", f"Expected '{greeting}' to route to chat, got {res.intent}"
        assert res.confidence >= 0.85


@pytest.mark.asyncio
async def test_intent_router_simple_explanations_route_to_chat():
    router = IntentRouter()
    for query in [
        "explain binary search",
        "can you explain what recursion is?",
        "what is a hashmap?",
        "help me plan my day",
        "what does this error mean?",
    ]:
        res = await router.classify(query)
        assert res.intent == "chat", f"Expected '{query}' to route to chat, got {res.intent}"


@pytest.mark.asyncio
async def test_intent_router_complex_decisions_route_to_solve():
    router = IntentRouter()
    for query in [
        "Should I choose a government job or start a business?",
        "Should I accept this internship or focus on my startup?",
        "Compare these three business strategies and recommend one.",
        "Analyze the risks and create a 2-year plan.",
        "Research the competing explanations and evaluate the evidence.",
        "I'm in college and deciding between a stable job and building a startup. Compare the financial risk, opportunity cost, learning, reversibility, and downside protection and give me a practical two-year plan.",
    ]:
        res = await router.classify(query)
        assert res.intent == "solve", f"Expected '{query}' to route to solve, got {res.intent}"
        assert res.confidence >= 0.85


@pytest.mark.asyncio
async def test_intent_router_architecture_routes_to_solve():
    router = IntentRouter()
    query = "Design a secure scalable university platform for 50,000 students."
    res = await router.classify(query)
    assert res.intent == "solve"
    assert "architectural" in res.reason.lower() or "multi-agent" in res.reason.lower()


# =============================================================================
# 2. Chat Continuity & Short-Term Memory Tests
# =============================================================================

@pytest.mark.asyncio
async def test_chat_continuity_in_conversation():
    import uuid
    store = MemoryStore()
    conv_id = f"test-convo-{uuid.uuid4()}"
    user_id = f"user-alice-{uuid.uuid4()}"

    # Message 1
    await store.add_message(conv_id, user_id, "user", "I am building a SaaS startup.")
    await store.add_message(conv_id, user_id, "assistant", "Great! What kind of SaaS?")

    # Message 2
    await store.add_message(conv_id, user_id, "user", "An AI tool for students.")

    # Retrieve history
    recent = await store.get_recent_messages(conv_id, user_id=user_id, limit=5)
    assert len(recent) == 3
    assert recent[0].content == "I am building a SaaS startup."
    assert recent[1].content == "Great! What kind of SaaS?"
    assert recent[2].content == "An AI tool for students."


# =============================================================================
# 3. Long-Term Memory Extraction Tests
# =============================================================================

@pytest.mark.asyncio
async def test_long_term_memory_extraction_durable_facts():
    extractor = MemoryExtractor()
    text = "My long-term goal is to build a SaaS startup after college."
    facts = extractor.extract_heuristically(text)
    assert len(facts) >= 1
    assert any("saas startup" in f["fact"].lower() for f in facts)
    assert any(f["category"] == MemoryCategory.CAREER_GOAL for f in facts)


@pytest.mark.asyncio
async def test_long_term_memory_extraction_filters_transient_comments():
    extractor = MemoryExtractor()
    for transient in ["I'm hungry.", "I'm tired today.", "I have an exam tomorrow.", "Today was stressful."]:
        facts = extractor.extract_heuristically(transient)
        assert len(facts) == 0, f"Transient comment '{transient}' was wrongly extracted as memory!"


def test_sanitize_sensitive_data_redacts_keys():
    text_with_key = "My API key is AIzaSyD1234567890123456789012345678901 and password is secretPassword123"
    sanitized = sanitize_sensitive_data(text_with_key)
    assert "AIzaSy" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized


# =============================================================================
# 4. Memory Retrieval & Relevance Filtering Tests
# =============================================================================

def test_memory_retrieval_relevance_matching():
    retriever = MemoryRetriever()
    memories = [
        MemoryItem(user_id="u1", memory="User wants to become a software entrepreneur.", category=MemoryCategory.CAREER_GOAL, importance=4),
        MemoryItem(user_id="u1", memory="User is a computer science student in college.", category=MemoryCategory.EDUCATION, importance=3),
        MemoryItem(user_id="u1", memory="User prefers practical code examples.", category=MemoryCategory.PREFERENCE, importance=4),
    ]

    # Query 1: Career decision -> Relevant career memories retrieved
    results_career = retriever.retrieve("Should I take this internship or focus on my startup?", memories)
    mem_texts = [m.memory for m in results_career]
    assert any("software entrepreneur" in t for t in mem_texts)

    # Query 2: Pure conceptual question -> Career goal NOT retrieved
    results_code = retriever.retrieve("Explain recursion in simple terms.", memories)
    for m in results_code:
        assert "software entrepreneur" not in m.memory.lower()


# =============================================================================
# 5. User Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_user_isolation_memories_and_conversations():
    store = MemoryStore()

    # User A stores a memory and a message
    await store.add_memory("user-A", "User A works at MegaCorp.", category=MemoryCategory.GENERAL)
    await store.add_message("convo-A", "user-A", "user", "Private message from User A")

    # User B stores a memory and a message
    await store.add_memory("user-B", "User B is building a fintech app.", category=MemoryCategory.PROJECT)
    await store.add_message("convo-B", "user-B", "user", "Private message from User B")

    # Verify User A cannot see User B's memories
    user_a_mems = await store.get_user_memories("user-A")
    assert all("fintech" not in m.memory for m in user_a_mems)
    assert any("MegaCorp" in m.memory for m in user_a_mems)

    # Verify User B cannot see User A's memories
    user_b_mems = await store.get_user_memories("user-B")
    assert all("MegaCorp" not in m.memory for m in user_b_mems)
    assert any("fintech" in m.memory for m in user_b_mems)

    # Verify User B cannot read User A's conversation messages
    user_b_reading_a = await store.get_recent_messages("convo-A", user_id="user-B")
    assert len(user_b_reading_a) == 0


# =============================================================================
# 6. Guest Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_guest_session_isolation():
    store = MemoryStore()

    # Guest 1 stores memory in session-1
    await store.add_memory("guest_user", "Guest 1 is exploring machine learning", session_id="session-1")

    # Guest 2 stores memory in session-2
    await store.add_memory("guest_user", "Guest 2 is asking about cooking recipes", session_id="session-2")

    # Guest 1 only sees session-1 memory
    mems_1 = await store.get_user_memories("guest_user", session_id="session-1")
    assert len(mems_1) == 1
    assert "machine learning" in mems_1[0].memory

    # Guest 2 only sees session-2 memory
    mems_2 = await store.get_user_memories("guest_user", session_id="session-2")
    assert len(mems_2) == 1
    assert "cooking recipes" in mems_2[0].memory

    # Neither can see the other's
    assert "cooking" not in mems_1[0].memory
    assert "machine learning" not in mems_2[0].memory


# =============================================================================
# 7. Personalized Solve Context Propagation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_solve_context_enrichment_reaches_solve_request():
    context_mgr = ContextManager()
    user_id = "user-startup-founder"

    # Add relevant memory to store
    from backend.memory.store import memory_store
    await memory_store.clear_user_memories(user_id)
    await memory_store.add_memory(
        user_id=user_id,
        memory="User wants to build a SaaS company after graduation.",
        category=MemoryCategory.CAREER_GOAL,
        importance=5,
    )

    enriched_context = await context_mgr.build_solve_context(
        user_id=user_id,
        problem="Should I accept this internship or focus on my startup?",
    )

    assert "[KNOWN USER CONTEXT" in enriched_context
    assert "SaaS company" in enriched_context

    # Verify that SolveRequest cleanly accepts the enriched context
    req = SolveRequest(
        problem="Should I accept this internship or focus on my startup?",
        user_id=user_id,
        context=enriched_context,
    )
    assert req.context == enriched_context
    assert "SaaS company" in req.context


# =============================================================================
# 8. API Endpoints & Regression Tests
# =============================================================================

def test_api_chat_endpoint_chat_mode(app_client):
    res = app_client.post("/api/chat", json={
        "message": "hello, what is CHAI?",
        "user_id": "test-user-chat",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "chat"
    assert "message" in data
    assert data["request_status"] == "completed"
    assert data["intent_result"]["intent"] == "chat"


def test_api_chat_endpoint_solve_mode(app_client):
    # Solve routing should trigger solve pipeline
    res = app_client.post("/api/chat", json={
        "message": "Should I choose a government job or start a business?",
        "user_id": "test-user-solve",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "solve"
    assert "final_synthesized_answer" in data
    assert data["intent_result"]["intent"] == "solve"


def test_existing_api_solve_endpoint_remains_operational(app_client):
    """Verifies that existing /api/solve endpoint is 100% backward compatible."""
    res = app_client.post("/api/solve", json={
        "problem": "What is the capital of France?",
    })
    assert res.status_code == 200
    data = res.json()
    assert "request_status" in data
    assert data["request_status"] == "completed"


# =============================================================================
# 9. Failure Handling & Resilience Tests
# =============================================================================

@pytest.mark.asyncio
async def test_chat_service_handles_model_failure_gracefully():
    service = LangChainChatService()
    with patch.object(service, "_get_chat_model") as mock_model_factory:
        mock_chain = AsyncMock()
        mock_chain.ainvoke.side_effect = RuntimeError("Simulated upstream quota error (HTTP 429)")
        service.prompt_template = mock_chain

        reply, memories = await service.generate_reply(
            message="Hello",
            user_id="user-fail-test",
        )
        assert "temporary issue" in reply.lower() or "error" in reply.lower()


@pytest.mark.asyncio
async def test_memory_extraction_failure_is_isolated():
    extractor = MemoryExtractor()
    with patch("backend.memory.extraction.memory_store.add_memory", side_effect=Exception("Database lock error")):
        # Should NOT raise an exception
        result = await extractor.extract_and_store(
            user_id="user-err",
            user_message="I want to build a startup",
        )
        assert isinstance(result, list)


# =============================================================================
# 10. PostgreSQL Durable Persistence Tests
# =============================================================================

from backend.db.database import init_db, get_engine
from backend.db.repositories import (
    ConversationRepository,
    MessageRepository,
    MemoryRepository,
    UserProfileRepository,
)


@pytest.mark.asyncio
async def test_db_conversation_and_messages_persistence():
    import uuid
    await init_db()
    user_id = f"user-persist-{uuid.uuid4()}"
    conv_id = f"convo-persist-{uuid.uuid4()}"

    # Save conversation
    convo = await ConversationRepository.save_conversation(
        user_id=user_id,
        conversation_id=conv_id,
        title="Durable Thread",
    )
    assert convo.id == conv_id
    assert convo.user_id == user_id

    # Save messages
    msg1 = await MessageRepository.save_message(
        user_id=user_id,
        conversation_id=conv_id,
        role="user",
        content="I am launching an AI startup.",
    )
    msg2 = await MessageRepository.save_message(
        user_id=user_id,
        conversation_id=conv_id,
        role="assistant",
        content="Exciting! What is your product?",
    )

    # Retrieve recent messages
    recent = await MessageRepository.get_recent_messages(conv_id, user_id=user_id, limit=5)
    assert len(recent) == 2
    assert recent[0].content == "I am launching an AI startup."
    assert recent[1].content == "Exciting! What is your product?"


@pytest.mark.asyncio
async def test_db_memory_crud_and_isolation():
    await init_db()
    user_a = "user-persist-A"
    user_b = "user-persist-B"

    # Save memory for User A
    mem_a = await MemoryRepository.save_memory(
        user_id=user_a,
        memory="User wants to build a SaaS startup.",
        category="career_goal",
        importance=5,
    )
    assert mem_a.user_id == user_a

    # Save memory for User B
    mem_b = await MemoryRepository.save_memory(
        user_id=user_b,
        memory="User is researching quantum computing algorithms.",
        category="project",
        importance=4,
    )
    assert mem_b.user_id == user_b

    # Verify strict isolation in DB
    mems_a = await MemoryRepository.get_user_memories(user_a)
    mems_b = await MemoryRepository.get_user_memories(user_b)

    assert any("SaaS startup" in m.memory for m in mems_a)
    assert all("quantum" not in m.memory for m in mems_a)

    assert any("quantum" in m.memory for m in mems_b)
    assert all("SaaS" not in m.memory for m in mems_b)

    # Delete memory
    deleted = await MemoryRepository.delete_memory(user_a, mem_a.id)
    assert deleted is True
    mems_a_after = await MemoryRepository.get_user_memories(user_a)
    assert all(m.id != mem_a.id for m in mems_a_after)


@pytest.mark.asyncio
async def test_db_user_profile_persistence():
    await init_db()
    user_id = "user-profile-test"

    # Create profile
    profile = await UserProfileRepository.get_or_create_profile(user_id, name="Alex", email="alex@test.com")
    assert profile.name == "Alex"

    # Update profile
    updated = await UserProfileRepository.update_profile(
        user_id,
        {"role": "Founder", "preferences": {"tone": "concise", "mode": "practical"}},
    )
    assert updated.role == "Founder"
    assert updated.preferences.get("tone") == "concise"


@pytest.mark.asyncio
async def test_real_persistence_across_store_reinitialization():
    """
    CRITICAL TEST: Proves that memory persists in database across
    complete MemoryStore destruction and reinitialization.
    """
    await init_db()
    user_id = "user-reinit-proof"
    mem_text = "User wants to build a SaaS startup."

    # 1. Use store instance 1 to add memory
    store1 = MemoryStore()
    await store1.clear_user_memories(user_id)
    added = await store1.add_memory(
        user_id=user_id,
        memory=mem_text,
        category=MemoryCategory.CAREER_GOAL,
        importance=5,
    )
    assert added is not None

    # 2. Completely destroy/abandon store1 and instantiate store2 (fresh cache)
    del store1
    store2 = MemoryStore()

    # 3. Query PostgreSQL via store2
    persisted_mems = await store2.get_user_memories(user_id)
    assert len(persisted_mems) > 0, "Memory was lost after store reinitialization!"
    assert any("SaaS startup" in m.memory for m in persisted_mems)

    # 4. Verify ContextManager retrieves it from the database
    context_mgr = ContextManager()
    relevant = await context_mgr.get_relevant_memories(
        user_id=user_id,
        query="Should I accept this internship or focus on my startup?",
    )
    assert len(relevant) > 0
    assert any("SaaS startup" in m.memory for m in relevant)

    # 5. Verify it reaches the enriched solve context
    solve_context = await context_mgr.build_solve_context(
        user_id=user_id,
        problem="Should I accept this internship?",
    )
    assert "SaaS startup" in solve_context
    assert "[KNOWN USER CONTEXT" in solve_context


@pytest.mark.asyncio
async def test_database_failure_handling_and_resilience():
    """Verifies that database connection issues log safely without crashing the user turn."""
    store = MemoryStore()
    user_id = "user-fail-resilience"

    with patch("backend.memory.store.MemoryRepository.save_memory", side_effect=Exception("Database connection timeout")):
        # Should NOT raise an unhandled exception to caller
        item = await store.add_memory(user_id, "User prefers Python", category=MemoryCategory.PREFERENCE)
        assert item is not None
        assert item.memory == "User prefers Python"


# =============================================================================
# 7. Dedicated LangChain Conversational Verification Tests
# =============================================================================

def test_langchain_structural_chain_components():
    """
    [CATEGORY A - STRUCTURAL TEST]
    Verifies that the LangChain conversational service explicitly constructs
    and uses the LCEL chain: ChatPromptTemplate | Model | StrOutputParser.
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.runnables import RunnableSequence
    from backend.chat.service import LangChainChatService

    service = LangChainChatService()
    assert isinstance(service.prompt_template, ChatPromptTemplate)

    chain = service.build_chain()
    assert isinstance(chain, RunnableSequence), f"Expected RunnableSequence, got {type(chain)}"
    step_types = [step.__class__.__name__ for step in chain.steps]
    assert "ChatPromptTemplate" in step_types
    assert "StrOutputParser" in step_types


def test_real_chat_mode_langchain_execution(app_client):
    """
    [CATEGORY B/C - EXECUTION TEST]
    Proves that POST /api/chat executes through LangChain chat mode
    and returns a valid conversational answer without triggering LangGraph coordinator.
    """
    with patch("backend.core.coordinator.CHAICoordinator.process_request") as mock_coord:
        res = app_client.post(
            "/api/chat",
            json={
                "message": "Explain recursion in simple terms.",
                "conversation_id": "langchain-test-1",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "chat"
        assert len(data["message"]) > 20
        assert mock_coord.call_count == 0, "LangGraph Coordinator must NOT be invoked during chat mode"


@pytest.mark.asyncio
async def test_conversation_memory_history_continuity(app_client):
    """
    [CATEGORY B/C - CONVERSATION MEMORY TEST]
    Proves that a second LangChain request in the same conversation_id
    receives the short-term conversation history from previous turns.
    """
    conv_id = "test-conv-memory-continuity"

    # Turn 1
    r1 = app_client.post(
        "/api/chat",
        json={
            "message": "My name is Alex and I am building an AI startup.",
            "conversation_id": conv_id,
        },
    )
    assert r1.status_code == 200

    # Turn 2
    r2 = app_client.post(
        "/api/chat",
        json={
            "message": "What am I building?",
            "conversation_id": conv_id,
        },
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["mode"] == "chat"
    # Inspect that history in context manager returned previous turn
    recent = await context_manager.get_recent_messages(conv_id)
    assert len(recent) >= 2
    assert any("AI startup" in msg.content for msg in recent)


@pytest.mark.asyncio
async def test_long_term_memory_injection_new_conversation():
    """
    [CATEGORY B/C - LONG-TERM MEMORY INJECTION]
    Verifies that durable PostgreSQL memory is retrieved and injected
    into context across fresh conversation sessions.
    """
    user_id = "user-lt-memory-test"
    await memory_store.clear_user_memories(user_id)
    await memory_store.add_memory(
        user_id,
        "User is a computer science student and long-term goal is to build a SaaS startup.",
        category=MemoryCategory.CAREER_GOAL,
        importance=5,
    )

    ctx = await context_manager.build_chat_context(
        user_id=user_id,
        query="Should I take this internship?",
        conversation_id="brand-new-convo-id",
    )
    assert len(ctx.relevant_memories) > 0
    assert any("SaaS startup" in m.memory for m in ctx.relevant_memories)
    assert "SaaS startup" in ctx.formatted_context_string


@pytest.mark.asyncio
async def test_irrelevant_memory_filtering_verification():
    """
    [CATEGORY B - RELEVANCE FILTERING]
    Proves that unrelated memories (e.g. Rust trading) are NOT injected into
    the LangChain prompt when asking an unrelated question (e.g. recursion).
    """
    user_id = "user-irrelevant-filter-test"
    await memory_store.clear_user_memories(user_id)
    await memory_store.add_memory(
        user_id,
        "User is interested in Rust trading systems.",
        category=MemoryCategory.PROJECT,
        importance=4,
    )

    ctx = await context_manager.build_chat_context(
        user_id=user_id,
        query="Explain recursion in simple terms.",
        conversation_id="rec-test-conv",
    )
    # Rust trading should NOT match recursion
    assert all("Rust" not in m.memory for m in ctx.relevant_memories)
    assert "Rust" not in ctx.formatted_context_string


def test_langchain_failure_handling_graceful(app_client):
    """
    [CATEGORY B - RESILIENCE TEST]
    Proves that a model/chain invocation failure does not crash the server
    and returns a graceful response to the client.
    """
    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke",
        side_effect=Exception("Simulated model outage"),
    ):
        res = app_client.post(
            "/api/chat",
            json={"message": "Explain recursion in simple terms."},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "chat"
        assert "temporary issue" in data["message"].lower() or "reasoning engine" in data["message"].lower()


def test_langchain_is_not_langgraph_boundary(app_client):
    """
    [CATEGORY B - ARCHITECTURE BOUNDARY TEST]
    Proves that:
    1. Simple chat queries route to LangChain (0 coordinator calls)
    2. Complex trade-off queries route to LangGraph (coordinator called)
    """
    from backend.core.schemas import FinalResponse

    mock_solve = FinalResponse(
        request_id="test-solve-1",
        problem="test",
        original_query="test",
        route="complex",
        complexity="high",
        execution_status="completed",
        completed_agents=["synthesizer"],
        final_synthesized_answer="Solve answer from 12 agents.",
    )

    with patch("backend.core.coordinator.CHAICoordinator.process_request", new_callable=AsyncMock) as mock_coord:
        mock_coord.return_value = mock_solve

        # 1. Simple explanation -> CHAT (LangChain)
        r_chat = app_client.post("/api/chat", json={"message": "Explain recursion in simple terms."})
        assert r_chat.status_code == 200
        assert r_chat.json()["mode"] == "chat"
        assert mock_coord.call_count == 0

        # 2. Complex trade-off query -> SOLVE (LangGraph)
        complex_msg = (
            "I'm deciding between a stable job and building a startup. "
            "Compare financial risk, opportunity cost, reversibility, and learning."
        )
        r_solve = app_client.post("/api/chat", json={"message": complex_msg})
        assert r_solve.status_code == 200
        assert r_solve.json()["mode"] == "solve"
        assert mock_coord.call_count == 1


