import { UserSession } from './auth-client'

declare global {
  interface Window {
    google?: {
      accounts: {
        oauth2: {
          initTokenClient: (config: {
            client_id: string
            scope: string
            callback: (response: {
              access_token?: string
              error?: string
              expires_in?: number
            }) => void
            error_callback?: (err: any) => void
          }) => {
            requestAccessToken: (overrideConfig?: { prompt?: string }) => void
          }
        }
        id: {
          initialize: (config: any) => void
          prompt: () => void
          renderButton: (parent: HTMLElement, options: any) => void
        }
      }
    }
  }
}

const STORAGE_KEY_GOOGLE_CLIENT_ID = 'chai_google_client_id'
const STORAGE_KEY_GITHUB_CLIENT_ID = 'chai_github_client_id'

export function getGoogleClientId(): string {
  try {
    const envId = (import.meta as any).env?.VITE_GOOGLE_CLIENT_ID
    if (envId && typeof envId === 'string' && envId.trim() && !envId.includes('your_')) {
      return envId.trim()
    }
    return localStorage.getItem(STORAGE_KEY_GOOGLE_CLIENT_ID)?.trim() || ''
  } catch {
    return ''
  }
}

export function setGoogleClientId(clientId: string) {
  try {
    if (clientId.trim()) {
      localStorage.setItem(STORAGE_KEY_GOOGLE_CLIENT_ID, clientId.trim())
    } else {
      localStorage.removeItem(STORAGE_KEY_GOOGLE_CLIENT_ID)
    }
  } catch {
    // ignore
  }
}

export function getGitHubClientId(): string {
  try {
    const envId = (import.meta as any).env?.VITE_GITHUB_CLIENT_ID
    if (envId && typeof envId === 'string' && envId.trim() && !envId.includes('your_')) {
      return envId.trim()
    }
    return localStorage.getItem(STORAGE_KEY_GITHUB_CLIENT_ID)?.trim() || ''
  } catch {
    return ''
  }
}

export function setGitHubClientId(clientId: string) {
  try {
    if (clientId.trim()) {
      localStorage.setItem(STORAGE_KEY_GITHUB_CLIENT_ID, clientId.trim())
    } else {
      localStorage.removeItem(STORAGE_KEY_GITHUB_CLIENT_ID)
    }
  } catch {
    // ignore
  }
}

/**
 * Ensures Google Identity Services (GSI) SDK is loaded on the page
 */
export async function ensureGoogleScriptLoaded(): Promise<boolean> {
  if (typeof window === 'undefined') return false
  if (window.google?.accounts?.oauth2) return true

  return new Promise((resolve) => {
    const existing = document.querySelector('script[src*="accounts.google.com/gsi/client"]')
    if (existing) {
      let attempts = 0
      const checkInterval = setInterval(() => {
        attempts++
        if (window.google?.accounts?.oauth2) {
          clearInterval(checkInterval)
          resolve(true)
        } else if (attempts > 30) {
          clearInterval(checkInterval)
          resolve(false)
        }
      }, 100)
      return
    }

    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.defer = true
    script.onload = () => {
      resolve(Boolean(window.google?.accounts?.oauth2))
    }
    script.onerror = () => resolve(false)
    document.head.appendChild(script)
  })
}

/**
 * Triggers authentic Google OAuth 2.0 popup via Google Identity Services
 */
export async function launchGoogleOAuthPopup(
  clientIdOverride?: string,
): Promise<{ user?: UserSession; error?: string; needsClientId?: boolean }> {
  const clientId = clientIdOverride || getGoogleClientId()

  if (!clientId) {
    return { needsClientId: true }
  }

  const loaded = await ensureGoogleScriptLoaded()
  if (!loaded || !window.google?.accounts?.oauth2) {
    return { error: 'Google Identity Services SDK could not be loaded.' }
  }

  return new Promise((resolve) => {
    try {
      const client = window.google!.accounts.oauth2.initTokenClient({
        client_id: clientId,
        scope: 'https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email openid',
        callback: async (tokenResponse) => {
          if (tokenResponse.error) {
            resolve({ error: `Google OAuth Error: ${tokenResponse.error}` })
            return
          }

          if (!tokenResponse.access_token) {
            resolve({ error: 'No access token received from Google.' })
            return
          }

          try {
            // Fetch authentic user profile from Google's standard UserInfo API
            const userInfoRes = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
              headers: {
                Authorization: `Bearer ${tokenResponse.access_token}`,
              },
            })

            if (!userInfoRes.ok) {
              resolve({ error: 'Failed to retrieve profile from Google UserInfo endpoint.' })
              return
            }

            const profile = await userInfoRes.json()

            const user: UserSession = {
              id: profile.sub || `goog_${Date.now()}`,
              name: profile.name || profile.given_name || 'Google User',
              email: profile.email || 'user@gmail.com',
              image: profile.picture || null,
              provider: 'google',
            }

            resolve({ user })
          } catch (err: any) {
            resolve({ error: err?.message || 'Error processing Google profile.' })
          }
        },
        error_callback: (err) => {
          resolve({ error: err?.message || 'Google Sign-In popup was closed or interrupted.' })
        },
      })

      // Prompt account selection like standard web applications
      client.requestAccessToken({ prompt: 'select_account' })
    } catch (err: any) {
      resolve({ error: err?.message || 'Failed to initialize Google token client.' })
    }
  })
}
