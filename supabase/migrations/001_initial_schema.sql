-- ============================================================
-- CHAI Platform — Initial Database Schema
-- Migration: 001_initial_schema.sql
--
-- Tables:
--   1. profiles          — user profiles linked to Supabase auth
--   2. solve_requests    — problems submitted to CHAI
--   3. agent_outputs     — per-agent results (researcher, strategist, engineer, guardian)
--   4. evaluations       — evaluator consistency/completeness results
--   5. security_findings — security layer findings (separate from guardian)
--   6. sources           — information/source records per request
--
-- All tables use UUIDs, JSONB for flexible AI output, and TIMESTAMPTZ.
-- Row Level Security is enabled on every table.
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ============================================================
-- 1. PROFILES
-- ============================================================

CREATE TABLE IF NOT EXISTS public.profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT,
    full_name   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.profiles IS 'User profiles linked 1:1 with Supabase auth.users.';


-- ============================================================
-- 2. SOLVE_REQUESTS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.solve_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    problem         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    selected_agents JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_answer    TEXT,
    limitations     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,

    CONSTRAINT solve_requests_status_check
        CHECK (status IN ('pending', 'running', 'completed', 'failed'))
);

COMMENT ON TABLE public.solve_requests IS 'Each row is one problem submitted to CHAI for solving.';


-- ============================================================
-- 3. AGENT_OUTPUTS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.agent_outputs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id        UUID NOT NULL REFERENCES public.solve_requests(id) ON DELETE CASCADE,
    agent_name        TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    output            JSONB,
    error_message     TEXT,
    execution_time_ms INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ,

    CONSTRAINT agent_outputs_agent_name_check
        CHECK (agent_name IN ('researcher', 'strategist', 'engineer', 'guardian')),

    CONSTRAINT agent_outputs_status_check
        CHECK (status IN ('pending', 'running', 'completed', 'failed'))
);

COMMENT ON TABLE public.agent_outputs IS 'One row per agent execution. Structured results live in the output JSONB column.';


-- ============================================================
-- 4. EVALUATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.evaluations (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id            UUID NOT NULL REFERENCES public.solve_requests(id) ON DELETE CASCADE,
    consistency_score     NUMERIC(5,2),
    completeness_score    NUMERIC(5,2),
    conflicts             JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_requirements  JSONB NOT NULL DEFAULT '[]'::jsonb,
    evaluation_output     JSONB,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.evaluations IS 'Evaluator results comparing outputs of the specialized agents.';


-- ============================================================
-- 5. SECURITY_FINDINGS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.security_findings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id      UUID NOT NULL REFERENCES public.solve_requests(id) ON DELETE CASCADE,
    severity        TEXT,
    category        TEXT,
    finding         TEXT,
    recommendation  TEXT,
    resolved        BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT security_findings_severity_check
        CHECK (severity IN ('low', 'medium', 'high', 'critical'))
);

COMMENT ON TABLE public.security_findings IS 'Security layer findings. Separate from the Guardian agent.';


-- ============================================================
-- 6. SOURCES
-- ============================================================

CREATE TABLE IF NOT EXISTS public.sources (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id  UUID NOT NULL REFERENCES public.solve_requests(id) ON DELETE CASCADE,
    title       TEXT,
    url         TEXT,
    source_type TEXT,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.sources IS 'Information/source records associated with a solve request.';


-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_solve_requests_user_id
    ON public.solve_requests(user_id);

CREATE INDEX IF NOT EXISTS idx_solve_requests_created_at
    ON public.solve_requests(created_at);

CREATE INDEX IF NOT EXISTS idx_agent_outputs_request_id
    ON public.agent_outputs(request_id);

CREATE INDEX IF NOT EXISTS idx_agent_outputs_agent_name
    ON public.agent_outputs(agent_name);

CREATE INDEX IF NOT EXISTS idx_evaluations_request_id
    ON public.evaluations(request_id);

CREATE INDEX IF NOT EXISTS idx_security_findings_request_id
    ON public.security_findings(request_id);

CREATE INDEX IF NOT EXISTS idx_sources_request_id
    ON public.sources(request_id);


-- ============================================================
-- ROW LEVEL SECURITY — enable on all tables
-- ============================================================

ALTER TABLE public.profiles          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.solve_requests    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_outputs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evaluations       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sources           ENABLE ROW LEVEL SECURITY;


-- ============================================================
-- RLS POLICIES — profiles
-- ============================================================

CREATE POLICY profiles_select_own ON public.profiles
    FOR SELECT
    USING (id = auth.uid());

CREATE POLICY profiles_update_own ON public.profiles
    FOR UPDATE
    USING (id = auth.uid());


-- ============================================================
-- RLS POLICIES — solve_requests
-- ============================================================

CREATE POLICY solve_requests_select_own ON public.solve_requests
    FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY solve_requests_insert_own ON public.solve_requests
    FOR INSERT
    WITH CHECK (user_id = auth.uid());


-- ============================================================
-- RLS POLICIES — agent_outputs
-- ============================================================

CREATE POLICY agent_outputs_select_own ON public.agent_outputs
    FOR SELECT
    USING (
        request_id IN (
            SELECT id FROM public.solve_requests
            WHERE user_id = auth.uid()
        )
    );


-- ============================================================
-- RLS POLICIES — evaluations
-- ============================================================

CREATE POLICY evaluations_select_own ON public.evaluations
    FOR SELECT
    USING (
        request_id IN (
            SELECT id FROM public.solve_requests
            WHERE user_id = auth.uid()
        )
    );


-- ============================================================
-- RLS POLICIES — security_findings
-- ============================================================

CREATE POLICY security_findings_select_own ON public.security_findings
    FOR SELECT
    USING (
        request_id IN (
            SELECT id FROM public.solve_requests
            WHERE user_id = auth.uid()
        )
    );


-- ============================================================
-- RLS POLICIES — sources
-- ============================================================

CREATE POLICY sources_select_own ON public.sources
    FOR SELECT
    USING (
        request_id IN (
            SELECT id FROM public.solve_requests
            WHERE user_id = auth.uid()
        )
    );


-- ============================================================
-- END OF MIGRATION
-- ============================================================
