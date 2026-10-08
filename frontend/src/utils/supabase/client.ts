import { createBrowserClient } from "@supabase/ssr";

const procEnv = (globalThis as any).process?.env;

const supabaseUrl =
  procEnv?.NEXT_PUBLIC_SUPABASE_URL ||
  (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_SUPABASE_URL) ||
  "https://lkgezucyebjyxatpdxzv.supabase.co";

const supabaseKey =
  procEnv?.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
  (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_SUPABASE_PUBLISHABLE_KEY) ||
  "sb_publishable_14pzQ29xt4ltYQZagF8qzw_nICbk-NC";

export const createClient = () =>
  createBrowserClient(
    supabaseUrl!,
    supabaseKey!,
  );
