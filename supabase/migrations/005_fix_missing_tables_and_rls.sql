-- ============================================================
-- CHAI Platform — Fix All Missing Tables + RLS Policies
-- Migration: 005_fix_missing_tables_and_rls.sql
-- Project: lkgezucyebjyxatpdxzv
--
-- Instructions:
--   1. Go to: https://supabase.com/dashboard/project/lkgezucyebjyxatpdxzv/sql/new
--   2. Paste this ENTIRE script and click "Run" (Ctrl+Enter)
-- ============================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 2. CREATE MISSING TABLES (if not already present)
-- ============================================================

-- 2.1 CONVERSATIONS
CREATE TABLE IF NOT EXISTS public.conversations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'guest_default',
    title       TEXT NOT NULL DEFAULT 'New Conversation',
    mode        TEXT NOT NULL DEFAULT 'ask',
    layout      TEXT NOT NULL DEFAULT 'chat',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.conversations IS 'Chat sessions and problem-solving threads.';
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON public.conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON public.conversations(updated_at DESC);

-- 2.2 MESSAGES
CREATE TABLE IF NOT EXISTS public.messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL DEFAULT 'guest_default',
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    attachments     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.messages IS 'Conversation messages.';
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON public.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON public.messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON public.messages(created_at ASC);

-- 2.3 FILES
CREATE TABLE IF NOT EXISTS public.files (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id         TEXT NOT NULL DEFAULT 'guest_default',
    conversation_id TEXT REFERENCES public.conversations(id) ON DELETE SET NULL,
    file_name       TEXT NOT NULL,
    file_type       TEXT,
    file_size       BIGINT,
    file_url        TEXT,
    storage_path    TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.files IS 'File metadata and attachments.';
CREATE INDEX IF NOT EXISTS idx_files_user_id ON public.files(user_id);

-- 2.4 MEMORIES
CREATE TABLE IF NOT EXISTS public.memories (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'guest_default',
    memory      TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    importance  INTEGER NOT NULL DEFAULT 3,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.memories IS 'Long-term user memories and facts.';
CREATE INDEX IF NOT EXISTS idx_memories_user_id ON public.memories(user_id);

-- 2.5 USER_PROFILES
CREATE TABLE IF NOT EXISTS public.user_profiles (
    user_id     TEXT PRIMARY KEY,
    name        TEXT,
    email       TEXT,
    role        TEXT,
    goals       JSONB NOT NULL DEFAULT '[]'::jsonb,
    interests   JSONB NOT NULL DEFAULT '[]'::jsonb,
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.user_profiles IS 'Detailed user profile and workspace configuration.';


-- ============================================================
-- 3. STORAGE BUCKET
-- ============================================================
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('chai-files', 'chai-files', true, 52428800, NULL)
ON CONFLICT (id) DO UPDATE SET public = true;


-- ============================================================
-- 4. AUTH TRIGGER — Auto-create profile on new Supabase auth user
-- ============================================================
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

-- Backfill existing auth users into profiles
INSERT INTO public.profiles (id, email, full_name, updated_at)
SELECT
  id,
  email,
  COALESCE(raw_user_meta_data->>'full_name', raw_user_meta_data->>'name', split_part(email, '@', 1)),
  NOW()
FROM auth.users
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- 5. ENABLE RLS ON ALL TABLES
-- ============================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.solve_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;


-- ============================================================
-- 6. OPEN RLS POLICIES (Allow all for development)
-- The backend uses the anon key — open policies allow writes.
-- Tighten these to user-scoped policies before going to production.
-- ============================================================

-- profiles
DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_insert_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_all_access" ON public.profiles;
DROP POLICY IF EXISTS "profiles_open_access" ON public.profiles;
CREATE POLICY "profiles_open_access" ON public.profiles FOR ALL USING (true) WITH CHECK (true);

-- solve_requests
DROP POLICY IF EXISTS "solve_requests_select_own" ON public.solve_requests;
DROP POLICY IF EXISTS "solve_requests_insert_own" ON public.solve_requests;
DROP POLICY IF EXISTS "solve_requests_all_access" ON public.solve_requests;
DROP POLICY IF EXISTS "solve_requests_open_access" ON public.solve_requests;
CREATE POLICY "solve_requests_open_access" ON public.solve_requests FOR ALL USING (true) WITH CHECK (true);

-- agent_outputs
DROP POLICY IF EXISTS "agent_outputs_select_own" ON public.agent_outputs;
DROP POLICY IF EXISTS "agent_outputs_all_access" ON public.agent_outputs;
DROP POLICY IF EXISTS "agent_outputs_open_access" ON public.agent_outputs;
CREATE POLICY "agent_outputs_open_access" ON public.agent_outputs FOR ALL USING (true) WITH CHECK (true);

-- evaluations
DROP POLICY IF EXISTS "evaluations_select_own" ON public.evaluations;
DROP POLICY IF EXISTS "evaluations_all_access" ON public.evaluations;
DROP POLICY IF EXISTS "evaluations_open_access" ON public.evaluations;
CREATE POLICY "evaluations_open_access" ON public.evaluations FOR ALL USING (true) WITH CHECK (true);

-- security_findings
DROP POLICY IF EXISTS "security_findings_select_own" ON public.security_findings;
DROP POLICY IF EXISTS "security_findings_all_access" ON public.security_findings;
DROP POLICY IF EXISTS "security_findings_open_access" ON public.security_findings;
CREATE POLICY "security_findings_open_access" ON public.security_findings FOR ALL USING (true) WITH CHECK (true);

-- sources
DROP POLICY IF EXISTS "sources_select_own" ON public.sources;
DROP POLICY IF EXISTS "sources_all_access" ON public.sources;
DROP POLICY IF EXISTS "sources_open_access" ON public.sources;
CREATE POLICY "sources_open_access" ON public.sources FOR ALL USING (true) WITH CHECK (true);

-- conversations
DROP POLICY IF EXISTS "conversations_open_access" ON public.conversations;
CREATE POLICY "conversations_open_access" ON public.conversations FOR ALL USING (true) WITH CHECK (true);

-- messages
DROP POLICY IF EXISTS "messages_open_access" ON public.messages;
CREATE POLICY "messages_open_access" ON public.messages FOR ALL USING (true) WITH CHECK (true);

-- files
DROP POLICY IF EXISTS "files_open_access" ON public.files;
CREATE POLICY "files_open_access" ON public.files FOR ALL USING (true) WITH CHECK (true);

-- memories
DROP POLICY IF EXISTS "memories_open_access" ON public.memories;
CREATE POLICY "memories_open_access" ON public.memories FOR ALL USING (true) WITH CHECK (true);

-- user_profiles
DROP POLICY IF EXISTS "user_profiles_open_access" ON public.user_profiles;
CREATE POLICY "user_profiles_open_access" ON public.user_profiles FOR ALL USING (true) WITH CHECK (true);

-- Storage
DROP POLICY IF EXISTS "chai_files_select" ON storage.objects;
CREATE POLICY "chai_files_select" ON storage.objects FOR SELECT USING (bucket_id = 'chai-files');
DROP POLICY IF EXISTS "chai_files_insert" ON storage.objects;
CREATE POLICY "chai_files_insert" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'chai-files');
DROP POLICY IF EXISTS "chai_files_update" ON storage.objects;
CREATE POLICY "chai_files_update" ON storage.objects FOR UPDATE USING (bucket_id = 'chai-files') WITH CHECK (bucket_id = 'chai-files');
DROP POLICY IF EXISTS "chai_files_delete" ON storage.objects;
CREATE POLICY "chai_files_delete" ON storage.objects FOR DELETE USING (bucket_id = 'chai-files');


-- ============================================================
-- 7. EXPLICIT GRANTS (required for anon/authenticated access)
-- ============================================================
GRANT ALL ON TABLE public.profiles TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.solve_requests TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.agent_outputs TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.evaluations TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.security_findings TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.sources TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.conversations TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.messages TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.files TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.memories TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.user_profiles TO anon, authenticated, service_role;

GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON SCHEMA public TO anon, authenticated, service_role;

-- ============================================================
-- Setup Complete!
-- ============================================================
