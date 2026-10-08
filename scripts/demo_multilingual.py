"""
Demonstration and Validation of CHAI Multilingual NLP Layer.
Tests English, Hindi, and Kannada inputs through the CHAI Coordinator pipeline.
"""

import os
import sys

# Ensure repository root is on Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from unittest.mock import AsyncMock, patch

from backend.core.coordinator import Coordinator
from backend.core.schemas import SolveRequest
from backend.agents.researcher.models import ResearchResult
from backend.agents.strategist.models import StrategyResult
from backend.agents.engineer.schemas import EngineerOutput
from backend.agents.guardian.schemas import GuardianOutput
from backend.agents.security.models import SecurityResult
from backend.agents.evaluator.schemas import EvaluatorOutput


async def run_multilingual_demo():
    coordinator = Coordinator()

    test_cases = [
        {
            "name": "English Test",
            "problem": "Build an AI assistant for my college.",
            "explicit_lang": None,
            "mock_strat": "Phase 1: Requirements analysis. Phase 2: MVP development with FastAPI and React.",
            "mock_arch": "FastAPI backend, React frontend, Supabase PostgreSQL, and Gemini API integration.",
            "mock_sec": "JWT authentication, TLS 1.3 in transit, and role-based access control.",
        },
        {
            "name": "Hindi Test",
            "problem": "मेरे कॉलेज के लिए एक AI सहायक बनाने में मेरी मदद करें।",
            "explicit_lang": None,
            "mock_strat": "चरण 1: आवश्यकता विश्लेषण। चरण 2: FastAPI और React के साथ MVP विकास।",
            "mock_arch": "FastAPI बैकएंड, React फ्रंटएंड, Supabase डेटाबेस और Gemini API एकीकरण।",
            "mock_sec": "JWT प्रमाणीकरण, TLS 1.3 एन्क्रिप्शन, और भूमिका-आधारित पहुँच नियंत्रण।",
        },
        {
            "name": "Kannada Test",
            "problem": "ನನ್ನ ಕಾಲೇಜಿಗಾಗಿ AI ಸಹಾಯಕವನ್ನು ನಿರ್ಮಿಸಲು ನನಗೆ ಸಹಾಯ ಮಾಡಿ.",
            "explicit_lang": None,
            "mock_strat": "ಹಂತ 1: ಅಗತ್ಯತೆಗಳ ವಿಶ್ಲೇಷಣೆ. ಹಂತ 2: FastAPI ಮತ್ತು React ಬಳಸಿ MVP ಅಭಿವೃದ್ಧಿ.",
            "mock_arch": "FastAPI ಬ್ಯಾಕೆಂಡ್‌, React ಫ್ರಂಟ್‌ಎಂಡ್‌, Supabase ಡೇಟಾಬೇಸ್ ಮತ್ತು Gemini API ಸಂಯೋಜನೆ.",
            "mock_sec": "JWT ದೃಢೀಕರಣ, TLS 1.3 ಎನ್‌ಕ್ರಿಪ್ಶನ್ ಮತ್ತು ಪಾತ್ರ-ಆಧಾರಿತ ಪ್ರವೇಶ ನಿಯಂತ್ರಣ.",
        },
    ]

    for tc in test_cases:
        print("=" * 60)
        print(f"TEST CASE: {tc['name']}")
        print(f"Problem: {tc['problem']}")
        print("=" * 60)

        req = SolveRequest(problem=tc["problem"], language=tc["explicit_lang"])

        mock_res = ResearchResult(
            agent="researcher",
            status="completed",
            key_findings=["College stakeholders: students, professors, administration"],
            user_needs=["Fast response times", "Multilingual Q&A"],
            constraints=["Low latency", "Data privacy"],
            assumptions=["Campus Wi-Fi is available"],
            open_questions=[],
            sources=[],
        )
        mock_strat = StrategyResult(
            agent="strategist",
            status="completed",
            strategy=tc["mock_strat"],
            priorities=["Core Q&A", "Authentication", "Deployment"],
            roadmap=[],
            tradeoffs=["Self-hosted vs Cloud-hosted"],
            success_metrics=["Response time < 1.5s"],
        )
        mock_eng = EngineerOutput(
            technical_architecture=tc["mock_arch"],
            recommended_technologies=["FastAPI", "React", "Supabase", "Gemini API"],
            components_and_apis=["REST API", "Database", "Auth"],
            data_flow="Client -> FastAPI -> Gemini API -> Client",
            implementation_plan=["Setup FastAPI", "Integrate Gemini API", "Deploy on Supabase"],
        )
        mock_guard = GuardianOutput(
            safety_and_privacy_risks=["Potential student PII leakage"],
            reliability_and_ethical_risks=["Hallucinated syllabus data"],
            unsafe_assumptions=[],
            limitations=["Only college-related queries supported"],
            recommended_mitigations=["Input sanitization", "Auditing"],
        )
        mock_sec = SecurityResult(
            agent="security",
            status="completed",
            security_summary=tc["mock_sec"],
            threats=["Prompt Injection", "Unauthorized Data Access"],
            mitigations=["Input quarantine", "JWT verification"],
        )
        mock_eval = EvaluatorOutput(
            agent="evaluator",
            status="completed",
            detected_contradictions=[],
        )

        with patch.object(coordinator.researcher, "run", AsyncMock(return_value=mock_res)), \
             patch.object(coordinator.strategist, "run", AsyncMock(return_value=mock_strat)), \
             patch.object(coordinator.engineer, "run", AsyncMock(return_value=mock_eng)), \
             patch.object(coordinator.guardian, "run", AsyncMock(return_value=mock_guard)), \
             patch.object(coordinator.security, "run", AsyncMock(return_value=mock_sec)), \
             patch.object(coordinator.evaluator, "run", AsyncMock(return_value=mock_eval)):

            response = await coordinator.process_request(req)

            print(f"Request Status: {response.request_status}")
            print(f"Detected / Resolved Language: {response.language}")
            print(f"Selected Agents: {response.selected_agents}")
            print("Agent Execution Statuses:")
            for s in response.agent_execution_statuses:
                print(f"  - {s.agent_name}: {s.status}")

            print("\nFinal Synthesized Answer:")
            print("-" * 40)
            print(response.final_synthesized_answer)
            print("-" * 40)
            print("\n")


if __name__ == "__main__":
    asyncio.run(run_multilingual_demo())
