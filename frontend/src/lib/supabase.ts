import { createClient, SupabaseClient } from '@supabase/supabase-js'
import { UserSession } from './auth-client'

const STORAGE_KEY_URL = 'chai_supabase_url'
const STORAGE_KEY_ANON = 'chai_supabase_anon_key'

export function getSupabaseConfig(): { url: string; anonKey: string } {
  let url = ''
  let anonKey = ''

  try {
    const envUrl = (import.meta as any).env?.VITE_SUPABASE_URL
    const envKey = (import.meta as any).env?.VITE_SUPABASE_ANON_KEY

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
      return { error: error.message, redirected: false, needsConfig: false }
    }

    if (data?.url) {
      // Browser redirects to the official OAuth provider authorization page
      window.location.href = data.url
      return { error: null, redirected: true, needsConfig: false }
    }

    return { error: null, redirected: true, needsConfig: false }
  } catch (err: any) {
    return { error: err?.message || 'Failed to start OAuth flow.', redirected: false, needsConfig: false }
  }
}

/**
 * Check if the URL has OAuth tokens (hash or query params) from Supabase redirect
 */
export async function handleSupabaseRedirectSession(): Promise<UserSession | null> {
  const supabase = getSupabaseClient()
  if (!supabase) return null

  try {
    const { data: { session }, error } = await supabase.auth.getSession()
    if (error || !session?.user) return null

    const user = session.user
    const provider = (user.app_metadata?.provider as any) || (user.user_metadata?.provider as any) || 'google'

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
      callback(userSession)
    }
  })

  return () => {
    subscription.unsubscribe()
  }
}
