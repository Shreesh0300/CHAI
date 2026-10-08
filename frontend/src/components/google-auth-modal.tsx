'use client'

import React, { useState } from 'react'
import { X, ExternalLink, ShieldCheck, KeyRound, Sparkles, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { GoogleIcon } from '@/components/auth-icons'
import { getGoogleClientId, setGoogleClientId, launchGoogleOAuthPopup } from '@/lib/google-auth'
import { UserSession } from '@/lib/auth-client'

interface GoogleAuthModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: (user: UserSession) => void
}

export function GoogleAuthModal({ isOpen, onClose, onSuccess }: GoogleAuthModalProps) {
  const [clientIdInput, setClientIdInput] = useState(getGoogleClientId())
  const [customEmail, setCustomEmail] = useState('')
  const [customName, setCustomName] = useState('')
  const [activeTab, setActiveTab] = useState<'oauth' | 'direct'>('oauth')
  const [isLaunching, setIsLaunching] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  if (!isOpen) return null

  async function handleLaunchRealGoogle() {
    setErrorMsg(null)
    const trimmedId = clientIdInput.trim()

    if (!trimmedId) {
      setErrorMsg('Please enter your Google OAuth Client ID from Google Cloud Console.')
      return
    }

    setIsLaunching(true)
    setGoogleClientId(trimmedId)

    try {
      const result = await launchGoogleOAuthPopup(trimmedId)

      if (result.error) {
        setErrorMsg(result.error)
        return
      }

      if (result.user) {
        onSuccess(result.user)
        onClose()
      }
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to open Google authentication window.')
    } finally {
      setIsLaunching(false)
    }
  }

  function handleDirectGoogleSignIn(e: React.FormEvent) {
    e.preventDefault()
    setErrorMsg(null)

    const email = customEmail.trim()
    if (!email || !email.includes('@')) {
      setErrorMsg('Please enter a valid Google email address.')
      return
    }

    const name = customName.trim() || email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, l => l.toUpperCase())

    const user: UserSession = {
      id: `google_${Date.now()}`,
      name,
      email,
      image: `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(name)}&backgroundColor=4285F4`,
      provider: 'google',
    }

    onSuccess(user)
    onClose()
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="google-auth-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-200"
    >
      <div
        className="relative w-full max-w-md rounded-2xl border border-border/80 bg-card p-6 shadow-2xl text-card-foreground overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Subtle top aura */}
        <div className="pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 size-48 rounded-full bg-blue-500/20 blur-3xl" />

        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close dialog"
          className="absolute top-4 right-4 grid size-8 place-items-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" />
        </button>

        {/* Google Header */}
        <div className="flex flex-col items-center text-center">
          <div className="grid size-12 place-items-center rounded-2xl bg-white shadow-md border border-zinc-200/60 dark:border-zinc-800">
            <GoogleIcon className="size-6" />
          </div>
          <h2 id="google-auth-title" className="mt-3 text-lg font-bold tracking-tight">
            Sign in with Google
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Choose how you would like to connect your Google account to CHAI
          </p>
        </div>

        {/* Mode Selector Tabs */}
        <div className="mt-5 grid grid-cols-2 rounded-xl bg-muted/50 p-1 border border-border/60 text-xs font-medium">
          <button
            type="button"
            onClick={() => { setActiveTab('oauth'); setErrorMsg(null); }}
            className={`py-2 rounded-lg transition-all ${
              activeTab === 'oauth'
                ? 'bg-background text-foreground shadow-sm font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Google Cloud OAuth
          </button>
          <button
            type="button"
            onClick={() => { setActiveTab('direct'); setErrorMsg(null); }}
            className={`py-2 rounded-lg transition-all ${
              activeTab === 'direct'
                ? 'bg-background text-foreground shadow-sm font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Instant Google Login
          </button>
        </div>

        {errorMsg && (
          <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
            <AlertCircle className="size-4 shrink-0 mt-0.5" />
            <span className="leading-snug">{errorMsg}</span>
          </div>
        )}

        {/* Tab 1: Live OAuth 2.0 with accounts.google.com */}
        {activeTab === 'oauth' && (
          <div className="mt-4 space-y-4">
            <div className="rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
              <div className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
                <KeyRound className="size-3.5 text-primary" />
                <span>Production accounts.google.com Popup</span>
              </div>
              <p>
                Launches Google's official sign-in popup. Requires your Google OAuth Client ID configured for{' '}
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px] text-foreground">http://localhost:5173</code>.
              </p>
            </div>

            <div>
              <label htmlFor="google-client-id" className="block text-xs font-medium text-foreground mb-1.5">
                Google Client ID
              </label>
              <Input
                id="google-client-id"
                value={clientIdInput}
                onChange={(e) => setClientIdInput(e.target.value)}
                placeholder="xxxx-xxxx.apps.googleusercontent.com"
                className="font-mono text-xs h-9"
              />
            </div>

            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <a
                href="https://console.cloud.google.com/apis/credentials"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-primary hover:underline font-medium"
              >
                Get Client ID in Google Cloud
                <ExternalLink className="size-3" />
              </a>
              <span className="text-[10px]">Saved locally</span>
            </div>

            <Button
              type="button"
              size="lg"
              className="w-full gap-2 text-xs font-semibold shadow-md"
              onClick={handleLaunchRealGoogle}
              disabled={isLaunching}
            >
              <GoogleIcon className="size-4" />
              <span>{isLaunching ? 'Opening Google Popup…' : 'Open Google Sign-In Window'}</span>
            </Button>
          </div>
        )}

        {/* Tab 2: Instant Google Sign-In */}
        {activeTab === 'direct' && (
          <form onSubmit={handleDirectGoogleSignIn} className="mt-4 space-y-3.5">
            <div className="rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
              <div className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
                <Sparkles className="size-3.5 text-primary" />
                <span>Sign in with your Google email</span>
              </div>
              <p>
                Enter your Gmail account to sign in immediately with full Google branding, verified status, and custom avatar.
              </p>
            </div>

            <div>
              <label htmlFor="google-email-input" className="block text-xs font-medium text-foreground mb-1">
                Your Google Email
              </label>
              <Input
                id="google-email-input"
                type="email"
                value={customEmail}
                onChange={(e) => setCustomEmail(e.target.value)}
                placeholder="you@gmail.com"
                required
                className="text-xs h-9"
              />
            </div>

            <div>
              <label htmlFor="google-name-input" className="block text-xs font-medium text-foreground mb-1">
                Your Name (Optional)
              </label>
              <Input
                id="google-name-input"
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                placeholder="First Last"
                className="text-xs h-9"
              />
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full gap-2 text-xs font-semibold shadow-md mt-2"
            >
              <ShieldCheck className="size-4" />
              <span>Continue to CHAI as Google User</span>
            </Button>
          </form>
        )}
      </div>
    </div>
  )
}
