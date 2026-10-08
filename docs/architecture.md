# CHAI Architecture Overview

For the complete multi-agent workflow guide, schemas, voice subsystem, and invariants, see [docs/gpt_workflow_guide.md](gpt_workflow_guide.md).

## Core Topology

```text
[Client / Voice / Web]
         │
         ▼
  FastAPI Gateway (backend/main.py)
         │
         ▼
  Coordinator (backend/core/coordinator.py)
   ├── Phase 1: ResearcherAgent || SecurityAgent
   ├── Phase 2: StrategistAgent
   ├── Phase 3: EngineerAgent || GuardianAgent
   ├── Phase 4: EvaluatorAgent
   └── Phase 5: Synthesizer (backend/synthesis/synthesizer.py)
         │
         ▼
  Supabase PostgreSQL Persistence (6 tables)
```

## Supported Languages
- English (`en`)
- Hindi (`hi`)
- Kannada (`kn` - native Kannada script strictly preserved)
- Sanskrit (`sa`)

## Voice Subsystem
- **STT**: `backend/voice/stt_service.py` (`gemini-flash-lite-latest`)
- **TTS**: `backend/voice/tts_service.py` (`gemini-3.8-flash-tts`)
