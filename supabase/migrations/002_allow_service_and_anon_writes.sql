-- ============================================================
-- CHAI Platform — Fix RLS Policies for Profiles & Solves
-- Migration: 002_allow_service_and_anon_writes.sql
--
-- Run this in your Supabase Dashboard -> SQL Editor
-- (https://supabase.com/dashboard/project/lkgezucyebjyxatpdxzv/sql/new)
-- ============================================================

-- 1. Automatic Profile Creation Trigger on Supabase Auth (Google, GitHub, Email)
-- Ensures whenever a user registers or logs in via Google/GitHub/email,
-- their public.profiles record is created/updated automatically.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, updated_at)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', split_part(NEW.email, '@', 1)),
    NOW()
  )
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = COALESCE(EXCLUDED.full_name, public.profiles.full_name),
    updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT OR UPDATE ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 2. Backfill existing auth users into profiles
INSERT INTO public.profiles (id, email, full_name, updated_at)
SELECT
  id,
  email,
  COALESCE(raw_user_meta_data->>'full_name', raw_user_meta_data->>'name', split_part(email, '@', 1)),
  NOW()
FROM auth.users
ON CONFLICT (id) DO NOTHING;

-- 3. PROFILES: Allow insert, select, and update
DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_insert_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_all_access" ON public.profiles;

CREATE POLICY "profiles_all_access" ON public.profiles
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- 4. SOLVE_REQUESTS: Allow insert and select
DROP POLICY IF EXISTS "solve_requests_select_own" ON public.solve_requests;
DROP POLICY IF EXISTS "solve_requests_insert_own" ON public.solve_requests;
DROP POLICY IF EXISTS "solve_requests_all_access" ON public.solve_requests;

CREATE POLICY "solve_requests_all_access" ON public.solve_requests
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- 5. AGENT_OUTPUTS: Allow insert and select
DROP POLICY IF EXISTS "agent_outputs_select_own" ON public.agent_outputs;
DROP POLICY IF EXISTS "agent_outputs_all_access" ON public.agent_outputs;

CREATE POLICY "agent_outputs_all_access" ON public.agent_outputs
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- 6. EVALUATIONS: Allow insert and select
DROP POLICY IF EXISTS "evaluations_select_own" ON public.evaluations;
DROP POLICY IF EXISTS "evaluations_all_access" ON public.evaluations;

CREATE POLICY "evaluations_all_access" ON public.evaluations
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- 7. SECURITY_FINDINGS: Allow insert and select
DROP POLICY IF EXISTS "security_findings_select_own" ON public.security_findings;
DROP POLICY IF EXISTS "security_findings_all_access" ON public.security_findings;

CREATE POLICY "security_findings_all_access" ON public.security_findings
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- 8. SOURCES: Allow insert and select
DROP POLICY IF EXISTS "sources_select_own" ON public.sources;
DROP POLICY IF EXISTS "sources_all_access" ON public.sources;

CREATE POLICY "sources_all_access" ON public.sources
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- ============================================================
-- Completed: RLS and Auth Triggers configured for CHAI platform
-- ============================================================
