# CHAI System Integration Specification & ChatGPT Prompt Guide

> **Instructions for your friend**: Copy and paste the prompt in **Section 1** directly into ChatGPT (or Claude) on your friend's system. It will instruct their AI to build and adapt their backend models and data according to your exact frontend architecture without breaking any existing features.

---

## 1. Direct Prompt to Copy-Paste into ChatGPT

```markdown
You are an expert AI Backend & Systems Architect. You are collaborating on the **CHAI (Coordinated Hybrid Agentic Intelligence)** platform. 

The frontend codebase is already completed, tested, and hosted at:
GitHub: https://github.com/Vishnuvforce/CHAI-front (Branch: main)

Your objective is to connect your local datasets, custom models, and agent pipeline to this frontend. You must strictly adhere to the architecture, API contracts, and constraints defined below so the frontend integrates seamlessly without any breaking changes.

### Key Architectural Guidelines & Rules:
1. **Do NOT modify or replace the frontend TTS voice system**: The frontend has a tuned, natural Web Speech Synthesis engine with premium Google/Natural voice selection that drives real-time audio waves, subtitles, and glowing orb states. Keep voice generation compatible with text streaming/responses.
2. **Wake Word & Speech Flow**: The frontend recognizes "Hey CHAI" / "Hi CHAI" and continuously listens. When user queries are submitted, the frontend calls `POST http://localhost:8000/api/solve` with JSON `{"problem": "<user speech text>"}`.
3. **CORS Configuration**: The backend must allow origins `["http://localhost:5173", "http://127.0.0.1:5173"]` with all headers and methods enabled (`allow_credentials=True`).
4. **Authentication Compatibility**: The frontend supports Supabase Google & GitHub OAuth and Guest Mode. Any backend auth or database persistence should expect JWT Bearer tokens or fall back gracefully for guest sessions (`guest@chai.ai`).
5. **Payload Contract**: Follow the exact `/api/solve` schema detailed in the API Contract section below.

Now, inspect the friend's local data and models, and help adapt/build the FastAPI backend endpoints to power CHAI according to this specification.
```

---

## 2. System Architecture Overview

```
 ┌───────────────────────────────────────────────────────────────┐
 │               CHAI Frontend (Port 5173 - React/Vite)          │
 │                                                               │
 │  ┌─────────────────┐   ┌───────────────────┐   ┌────────────┐ │
 │  │ STT Engine      │   │ 3D Thinking Orb   │   │ Screen Edge│ │
 │  │ "Hey CHAI" wake │──▶│ Idle ➔ Listening  │──▶│ Subtle Glow│ │
 │  │ Continuous mic  │   │ ➔ Thinking ➔ Speak│   │ & Particles│ │
 │  └─────────────────┘   └───────────────────┘   └────────────┘ │
 │          │                       ▲                            │
 │          ▼                       │                            │
 │   User Transcript          AI Answer Text                     │
 │          │                       │                            │
 └──────────┼───────────────────────┼────────────────────────────┘
            │ POST /api/solve       │ TTS Voice Output
            ▼                       │
 ┌───────────────────────────────────────────────────────────────┐
 │               CHAI Backend (Port 8000 - FastAPI)              │
 │                                                               │
 │  ┌──────────────┐  ┌─────────────┐  ┌───────────────────────┐ │
 │  │ Coordinator  │─▶│ Multi-Agent │─▶│ Synthesis & Sources   │ │
 │  │ Orchestrator │  │ Pipeline    │  │ Knowledge Graph / DB  │ │
 │  └──────────────┘  └─────────────┘  └───────────────────────┘ │
 └───────────────────────────────────────────────────────────────┘
```

---

## 3. Exact API Contracts

### A. Primary Problem Solving Endpoint: `POST /api/solve`

The frontend calls this endpoint immediately when a voice command or text prompt is recognized.

- **URL**: `http://localhost:8000/api/solve`
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`

#### Request Schema
```json
{
  "problem": "Explain the deployment architecture of our autonomous cluster"
}
```

#### Response Schema (FastAPI `FinalResponse`)
```json
{
  "request_status": "success",
  "selected_agents": [
    "Researcher",
    "Strategist",
    "SecurityGuardian"
  ],
  "agent_outputs": {
    "researcher": "Extracted 14 nodes from internal knowledge graphs.",
    "strategist": "Formulated optimized deployment trajectory.",
    "security": "Verified zero CVE vulnerabilities in target environment."
  },
  "retrieved_sources": [
    "CHAI Knowledge Graph",
    "Internal Technical Specifications",
    "Supabase Vector Store"
  ],
  "agent_execution_statuses": [
    { "agent_name": "Researcher", "status": "completed", "error": null },
    { "agent_name": "Strategist", "status": "completed", "error": null },
    { "agent_name": "SecurityGuardian", "status": "completed", "error": null }
  ],
  "evaluation_findings": null,
  "security_findings": null,
  "detected_conflicts": [],
  "final_synthesized_answer": "The autonomous cluster deployment consists of a multi-tier hybrid architecture orchestrated via FastAPI nodes...",
  "limitations": null
}
```

> **Crucial Field**: `final_synthesized_answer` is read directly by the frontend to display in the chat transcript and speak out loud via the TTS voice engine.

---

### B. Health Check Endpoint: `GET /api/health`
Used by the frontend and monitoring systems to verify backend availability.

- **URL**: `http://localhost:8000/api/health`
- **Method**: `GET`
- **Response**:
```json
{
  "status": "ok",
  "service": "chai-backend"
}
```

---

### C. Optional: Custom Backend STT Endpoint (If Friend Has Trained Speech Models)

If your friend has a custom-trained model (e.g. Whisper, Conformer, or fine-tuned language models) that should replace or augment the browser's native STT:

- **URL**: `http://localhost:8000/api/stt`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Form Data**: `file` (Audio blob: `.wav`, `.webm`, or `.mp3`)
- **Response Schema**:
```json
{
  "transcript": "hey chai analyze system health",
  "detected_language": "en",
  "confidence": 0.98,
  "wake_word_detected": true
}
```

---

## 4. State & UI Synchronization Rules

1. **Voice State Machine**:
   - `idle`: Microphone inactive.
   - `listening`: Actively listening for voice (Illumination & subtle edge particles pulse gently).
   - `thinking`: Query is being processed by backend `POST /api/solve` (Orb displays rotating neural aura).
   - `speaking`: Backend response is returned; speech synthesis is active (Orb displays audio waves, particles illuminate with selected Workspace Accent).
2. **Workspace Accents**:
   - The user selects one of 5 accent themes (`violet`, `blue`, `teal`, `rose`, `amber`).
   - All particle effects and visual glows dynamically adapt to this color.
3. **Session ID & Auth**:
   - Guest users have session ID `#guest_...`.
   - Google & GitHub users pass user profile info (`name`, `email`, `avatar`).

---

## 5. Quick Verification Commands for Your Friend

Your friend can run these commands on their terminal to verify their backend matches the frontend:

```bash
# 1. Health check
curl -X GET http://localhost:8000/api/health

# 2. Test solve pipeline
curl -X POST http://localhost:8000/api/solve \
  -H "Content-Type: application/json" \
  -d '{"problem": "Test query from CHAI frontend"}'
```
