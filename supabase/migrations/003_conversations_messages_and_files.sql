-- ============================================================
-- CHAI Platform — Conversations, Messages, Files & Storage Migration
-- Migration: 003_conversations_messages_and_files.sql
--
-- Tables created:
--   1. conversations  — chat threads & problem sessions
--   2. messages       — individual chat messages & attachments
--   3. files          — uploaded documents, images, and attachments
--   4. memories       — long-term user memories & learned facts
--   5. user_profiles  — user preferences, roles, and interests
--
-- Storage:
--   - chai-files bucket for file attachments
--
-- Permissions:
--   - RLS enabled with full CRUD policies for authenticated and anon roles
--   - Explicit GRANT statements for Supabase PostgREST Data API exposure
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. CONVERSATIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS public.conversations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT 'New Conversation',
    mode        TEXT NOT NULL DEFAULT 'ask',
    layout      TEXT NOT NULL DEFAULT 'chat',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.conversations IS 'Chat sessions and problem-solving threads.';

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON public.conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON public.conversations(updated_at DESC);


-- ============================================================
-- 2. MESSAGES
-- ============================================================
CREATE TABLE IF NOT EXISTS public.messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    attachments     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.messages IS 'Short-term and persistent conversation messages.';

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON public.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON public.messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON public.messages(created_at ASC);


-- ============================================================
-- 3. FILES (Attachments & Uploads)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.files (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id         TEXT NOT NULL,
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

COMMENT ON TABLE public.files IS 'Metadata and URLs for uploaded user files and chat attachments.';

CREATE INDEX IF NOT EXISTS idx_files_user_id ON public.files(user_id);
CREATE INDEX IF NOT EXISTS idx_files_conversation_id ON public.files(conversation_id);


-- ============================================================
-- 4. MEMORIES
-- ============================================================
CREATE TABLE IF NOT EXISTS public.memories (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    memory      TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    importance  INTEGER NOT NULL DEFAULT 3,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.memories IS 'Durable extracted facts and long-term user memories.';

CREATE INDEX IF NOT EXISTS idx_memories_user_id ON public.memories(user_id);


-- ============================================================
-- 5. USER_PROFILES
-- ============================================================
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
-- 6. STORAGE BUCKET FOR FILES (chai-files)
-- ============================================================
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'chai-files',
    'chai-files',
    true,
    52428800, -- 50 MB
    NULL
)
ON CONFLICT (id) DO UPDATE SET public = true;


-- ============================================================
-- 7. ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================

-- Enable RLS
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.solve_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sources ENABLE ROW LEVEL SECURITY;

-- Allow unrestricted CRUD for authenticated and anon clients
DROP POLICY IF EXISTS "conversations_open_access" ON public.conversations;
CREATE POLICY "conversations_open_access" ON public.conversations FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "messages_open_access" ON public.messages;
CREATE POLICY "messages_open_access" ON public.messages FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "files_open_access" ON public.files;
CREATE POLICY "files_open_access" ON public.files FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "memories_open_access" ON public.memories;
CREATE POLICY "memories_open_access" ON public.memories FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "user_profiles_open_access" ON public.user_profiles;
CREATE POLICY "user_profiles_open_access" ON public.user_profiles FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "solve_requests_open_access" ON public.solve_requests;
CREATE POLICY "solve_requests_open_access" ON public.solve_requests FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "agent_outputs_open_access" ON public.agent_outputs;
CREATE POLICY "agent_outputs_open_access" ON public.agent_outputs FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "evaluations_open_access" ON public.evaluations;
CREATE POLICY "evaluations_open_access" ON public.evaluations FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "security_findings_open_access" ON public.security_findings;
CREATE POLICY "security_findings_open_access" ON public.security_findings FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "sources_open_access" ON public.sources;
CREATE POLICY "sources_open_access" ON public.sources FOR ALL USING (true) WITH CHECK (true);


-- Storage RLS Policies
DROP POLICY IF EXISTS "chai_files_select" ON storage.objects;
CREATE POLICY "chai_files_select" ON storage.objects
    FOR SELECT USING (bucket_id = 'chai-files');

DROP POLICY IF EXISTS "chai_files_insert" ON storage.objects;
CREATE POLICY "chai_files_insert" ON storage.objects
    FOR INSERT WITH CHECK (bucket_id = 'chai-files');

DROP POLICY IF EXISTS "chai_files_update" ON storage.objects;
CREATE POLICY "chai_files_update" ON storage.objects
    FOR UPDATE USING (bucket_id = 'chai-files') WITH CHECK (bucket_id = 'chai-files');

DROP POLICY IF EXISTS "chai_files_delete" ON storage.objects;
CREATE POLICY "chai_files_delete" ON storage.objects
    FOR DELETE USING (bucket_id = 'chai-files');


-- ============================================================
-- 8. EXPLICIT GRANTS TO ANON & AUTHENTICATED ROLES
-- ============================================================
GRANT ALL ON TABLE public.conversations TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.messages TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.files TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.memories TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.user_profiles TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.profiles TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.solve_requests TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.agent_outputs TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.evaluations TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.security_findings TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.sources TO anon, authenticated, service_role;

GRANT ALL ON SCHEMA public TO anon, authenticated, service_role;
