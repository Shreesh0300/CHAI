import { createClient, SupabaseClient } from '@supabase/supabase-js'
import { UserSession } from './auth-client'

const STORAGE_KEY_URL = 'chai_supabase_url'
const STORAGE_KEY_ANON = 'chai_supabase_anon_key'

export function getSupabaseConfig(): { url: string; anonKey: string } {
  let url = ''
  let anonKey = ''

  try {
    const metaEnv = (import.meta as any).env || {}
    const envUrl = metaEnv.VITE_SUPABASE_URL || metaEnv.NEXT_PUBLIC_SUPABASE_URL
    const envKey =
      metaEnv.VITE_SUPABASE_ANON_KEY ||
      metaEnv.VITE_SUPABASE_PUBLISHABLE_KEY ||
      metaEnv.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
      metaEnv.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY

    if (envUrl && typeof envUrl === 'string' && !envUrl.includes('your_') && !envUrl.includes('your-')) {
      url = envUrl.trim()
    }
    if (envKey && typeof envKey === 'string' && !envKey.includes('your_') && !envKey.includes('your-')) {
      anonKey = envKey.trim()
    }
  } catch {
    // ignore
  }

  if (!url && typeof window !== 'undefined') {
    url = localStorage.getItem(STORAGE_KEY_URL)?.trim() || ''
  }
  if (!anonKey && typeof window !== 'undefined') {
    anonKey = localStorage.getItem(STORAGE_KEY_ANON)?.trim() || ''
  }

  // Project defaults for lkgezucyebjyxatpdxzv
  if (!url) {
    url = 'https://lkgezucyebjyxatpdxzv.supabase.co'
  }
  if (!anonKey) {
    anonKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxrZ2V6dWN5ZWJqeXhhdHBkeHp2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE0MDEyNDEsImV4cCI6MjEwNjk3NzI0MX0.p61gtCFBhYnsTuEQPSQiWzQEPF5K4XgH-Joc1qz_3XY'
  }

  return { url, anonKey }
}

export function saveSupabaseConfig(url: string, anonKey: string) {
  if (typeof window === 'undefined') return
  if (url.trim()) {
    localStorage.setItem(STORAGE_KEY_URL, url.trim())
  } else {
    localStorage.removeItem(STORAGE_KEY_URL)
  }

  if (anonKey.trim()) {
    localStorage.setItem(STORAGE_KEY_ANON, anonKey.trim())
  } else {
    localStorage.removeItem(STORAGE_KEY_ANON)
  }
}

let _clientInstance: SupabaseClient | null = null
let _lastUrl = ''
let _lastKey = ''

export function getSupabaseClient(): SupabaseClient | null {
  const { url, anonKey } = getSupabaseConfig()

  if (!url || !anonKey) {
    return null
  }

  if (_clientInstance && _lastUrl === url && _lastKey === anonKey) {
    return _clientInstance
  }

  try {
    _clientInstance = createClient(url, anonKey, {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
      },
    })
    _lastUrl = url
    _lastKey = anonKey
    return _clientInstance
  } catch (err) {
    console.warn('[Supabase] Failed to initialize client:', err)
    return null
  }
}

/**
 * Universal exported Supabase client instance/proxy.
 * Works seamlessly for components importing `{ supabase } from "@/lib/supabase"`.
 */
export const supabase = new Proxy({} as SupabaseClient, {
  get(_target, prop) {
    const client = getSupabaseClient()
    if (!client) {
      if (prop === 'auth') {
        return {
          getSession: async () => ({ data: { session: null }, error: null }),
          getUser: async () => ({ data: { user: null }, error: null }),
          onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
          signInWithOAuth: async () => ({ data: null, error: new Error('Supabase not configured') }),
          signOut: async () => ({ error: null }),
        }
      }
      return undefined
    }
    const val = (client as any)[prop]
    return typeof val === 'function' ? val.bind(client) : val
  },
})


/**
 * Initiates standard Supabase OAuth with Google or GitHub
 */
export async function signInWithSupabaseOAuth(
  provider: 'google' | 'github',
  customConfig?: { url: string; anonKey: string },
): Promise<{ error: string | null; redirected: boolean; needsConfig: boolean }> {
  if (customConfig) {
    saveSupabaseConfig(customConfig.url, customConfig.anonKey)
  }

  const supabase = getSupabaseClient()
  if (!supabase) {
    return { error: null, redirected: false, needsConfig: true }
  }

  try {
    const { url: currentUrl, anonKey: currentAnonKey } = getSupabaseConfig()
    const redirectTo = `${window.location.origin}/workspace`
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo,
        queryParams: {
          access_type: 'offline',
          prompt: 'consent',
        },
      },
    })

    if (error) {
      const errMsg = error.message
      if (errMsg.includes('missing OAuth secret')) {
        return {
          error: `Missing OAuth Secret: Your Supabase project is missing the ${provider === 'google' ? 'Google' : 'GitHub'} Client Secret. Configure it in Supabase Dashboard -> Authentication -> Providers -> ${provider === 'google' ? 'Google' : 'GitHub'}, or use Instant Sign-In.`,
          redirected: false,
          needsConfig: true,
        }
      }
      return { error: errMsg, redirected: false, needsConfig: false }
    }

    if (data?.url) {
      // Pre-check authorization endpoint to catch "missing OAuth secret" or "provider is not enabled"
      // before redirecting the browser to an ugly raw JSON error page.
      try {
        const testRes = await fetch(data.url, {
          method: 'GET',
          headers: { apikey: currentAnonKey },
        })
        if (!testRes.ok) {
          const errData = await testRes.json().catch(() => null)
          if (errData && errData.error_code === 'validation_failed') {
            const rawMsg = errData.msg || ''
            if (rawMsg.includes('missing OAuth secret')) {
              return {
                error: `Missing OAuth Secret in Supabase: In your Supabase Dashboard -> Authentication -> Providers -> ${provider === 'google' ? 'Google' : 'GitHub'}, enter both your Client ID and Client Secret from ${provider === 'google' ? 'Google Cloud Console' : 'GitHub Developer Settings'}, or use Instant Sign-In.`,
                redirected: false,
                needsConfig: true,
              }
            }
            if (rawMsg.includes('not enabled')) {
              return {
                error: `${provider === 'google' ? 'Google' : 'GitHub'} OAuth is not enabled in your Supabase project. Please toggle it ON in Supabase Dashboard -> Authentication -> Providers, or use Instant Sign-In.`,
                redirected: false,
                needsConfig: true,
              }
            }
            return {
              error: `Supabase Configuration Notice: ${rawMsg}`,
              redirected: false,
              needsConfig: true,
            }
          }
        }
      } catch {
        // If pre-flight has CORS or network redirect, proceed with standard navigation
      }

      // Browser redirects to the official OAuth provider authorization page
      window.location.href = data.url
      return { error: null, redirected: true, needsConfig: false }
    }

    return { error: null, redirected: true, needsConfig: false }
  } catch (err: any) {
    const raw = err?.message || 'Failed to start OAuth flow.'
    if (raw.includes('missing OAuth secret')) {
      return {
        error: `Missing OAuth Secret in Supabase: Configure your ${provider === 'google' ? 'Google' : 'GitHub'} Client Secret in Supabase Dashboard, or use Instant Sign-In.`,
        redirected: false,
        needsConfig: true,
      }
    }
    return { error: raw, redirected: false, needsConfig: false }
  }
}

import { getApiBaseUrl } from './api'

/**
 * Check if the URL has OAuth tokens (hash or query params) from Supabase redirect
 */
export async function handleSupabaseRedirectSession(): Promise<UserSession | null> {
  const supabase = getSupabaseClient()
  if (!supabase) return null

  try {
    const { data: { session }, error } = await supabase.auth.getSession()
    if (error || !session?.user) return null

    if (session.access_token && typeof window !== 'undefined') {
      localStorage.setItem('chai_access_token', session.access_token)
    }

    const user = session.user
    const provider = (user.app_metadata?.provider as any) || (user.user_metadata?.provider as any) || 'google'

    const name =
      user.user_metadata?.full_name ||
      user.user_metadata?.name ||
      user.email?.split('@')[0] ||
      'Operator'

    const userSession: UserSession = {
      id: user.id,
      name,
      email: user.email || '',
      image: user.user_metadata?.avatar_url || user.user_metadata?.picture || null,
      provider: provider === 'github' ? 'github' : 'google',
    }

    // Try fetching existing profile from Supabase to preserve custom display names
    try {
      const existing = await fetchUserProfile(user.id)
      if (existing && existing.full_name) {
        userSession.name = existing.full_name
      }
    } catch {}

    // Upsert to ensure profile is stored in Supabase
    upsertUserProfile(userSession).catch(() => {})

    return userSession
  } catch {
    return null
  }
}

/**
 * Listen for Supabase auth state changes in real time
 */
export function subscribeToSupabaseAuth(callback: (user: UserSession | null) => void): () => void {
  const supabase = getSupabaseClient()
  if (!supabase) return () => {}

  const {
    data: { subscription },
  } = supabase.auth.onAuthStateChange(async (_event, session) => {
    if (session?.user) {
      if (session.access_token && typeof window !== 'undefined') {
        localStorage.setItem('chai_access_token', session.access_token)
      }
      const user = session.user
      const provider =
        (user.app_metadata?.provider as any) || (user.user_metadata?.provider as any) || 'google'

      const userSession: UserSession = {
        id: user.id,
        name:
          user.user_metadata?.full_name ||
          user.user_metadata?.name ||
          user.email?.split('@')[0] ||
          'Operator',
        email: user.email || '',
        image: user.user_metadata?.avatar_url || user.user_metadata?.picture || null,
        provider: provider === 'github' ? 'github' : 'google',
      }

      fetchUserProfile(user.id).then((p) => {
        if (p && p.full_name) {
          userSession.name = p.full_name
          callback(userSession)
        }
      }).catch(() => {})

      upsertUserProfile(userSession).catch(() => {})
      callback(userSession)
    }
  })

  return () => {
    subscription.unsubscribe()
  }
}

/**
 * Upsert user profile into public.profiles in Supabase.
 * Uses both direct Supabase client (with user session) and backend sync.
 */
export async function upsertUserProfile(user: UserSession): Promise<boolean> {
  if (!user || !user.id) return false

  let success = false
  const client = getSupabaseClient()
  if (client) {
    try {
      const { error } = await client.from('profiles').upsert({
        id: user.id,
        email: user.email,
        full_name: user.name,
        updated_at: new Date().toISOString(),
      })
      if (!error) {
        success = true
      }
    } catch {
      // Continue to backend fallback
    }
  }

  // Also sync to backend /api/auth/sync-profile
  try {
    const token = typeof window !== 'undefined' ? localStorage.getItem('chai_access_token') : null
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${getApiBaseUrl()}/api/auth/sync-profile`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        id: user.id,
        email: user.email,
        name: user.name,
      }),
    })
    if (res.ok) success = true
  } catch {
    // ignore
  }

  return success
}

/**
 * Fetch user profile from Supabase public.profiles table.
 */
export async function fetchUserProfile(
  userId: string,
): Promise<{ id: string; email: string; full_name: string } | null> {
  if (!userId) return null

  const client = getSupabaseClient()
  if (client) {
    try {
      const { data, error } = await client
        .from('profiles')
        .select('*')
        .eq('id', userId)
        .maybeSingle()
      if (!error && data) {
        return {
          id: data.id,
          email: data.email || '',
          full_name: data.full_name || '',
        }
      }
    } catch {
      // fallback
    }
  }

  try {
    const token = typeof window !== 'undefined' ? localStorage.getItem('chai_access_token') : null
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${getApiBaseUrl()}/api/auth/profile?user_id=${encodeURIComponent(userId)}`, {
      headers,
    })
    if (res.ok) {
      const data = await res.json()
      if (data && data.id) {
        return {
          id: data.id,
          email: data.email || '',
          full_name: data.full_name || '',
        }
      }
    }
  } catch {
    // ignore
  }

  return null
}

/**
 * Fetch full solve details including multi-agent outputs, evaluations, and security posture.
 */
export async function fetchSolveDetails(solveId: string): Promise<any | null> {
  if (!solveId) return null

  try {
    const token = typeof window !== 'undefined' ? localStorage.getItem('chai_access_token') : null
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${getApiBaseUrl()}/api/solve/${encodeURIComponent(solveId)}`, {
      headers,
    })
    if (res.ok) {
      return await res.json()
    }
  } catch {}

  // Direct Supabase fallback
  const client = getSupabaseClient()
  if (client) {
    try {
      const { data: solve } = await client.from('solve_requests').select('*').eq('id', solveId).maybeSingle()
      if (solve) {
        const { data: outputs } = await client.from('agent_outputs').select('*').eq('request_id', solveId)
        const { data: evals } = await client.from('evaluations').select('*').eq('request_id', solveId).maybeSingle()
        const { data: security } = await client.from('security_findings').select('*').eq('request_id', solveId)
        const { data: sources } = await client.from('sources').select('*').eq('request_id', solveId)

        const agentOutputs: Record<string, any> = {}
        if (outputs) {
          outputs.forEach((o: any) => {
            if (o.agent_name) agentOutputs[o.agent_name] = o.output
          })
        }

        return {
          ...solve,
          agent_outputs: agentOutputs,
          evaluations: evals,
          security_findings: security || [],
          sources: sources || [],
        }
      }
    } catch {}
  }

  return null
}
