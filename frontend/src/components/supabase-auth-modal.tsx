'use client'

import React, { useState } from 'react'
import { X, ExternalLink, ShieldCheck, Database, Sparkles, AlertCircle, LoaderCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { GoogleIcon, GitHubIcon } from '@/components/auth-icons'
import { getSupabaseConfig, signInWithSupabaseOAuth, saveSupabaseConfig } from '@/lib/supabase'
import { UserSession } from '@/lib/auth-client'

interface SupabaseAuthModalProps {
  isOpen: boolean
  provider: 'google' | 'github'
  onClose: () => void
  onSuccess: (user: UserSession) => void
}

export function SupabaseAuthModal({
  isOpen,
  provider,
  onClose,
  onSuccess,
}: SupabaseAuthModalProps) {
  const initialConfig = getSupabaseConfig()
  const [supabaseUrl, setSupabaseUrl] = useState(initialConfig.url)
  const [anonKey, setAnonKey] = useState(initialConfig.anonKey)
  const [customEmail, setCustomEmail] = useState('')
  const [customName, setCustomName] = useState('')
  const [activeTab, setActiveTab] = useState<'supabase' | 'demo'>('supabase')
  const [isLoading, setIsLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  if (!isOpen) return null

  const isGoogle = provider === 'google'

  async function handleLaunchOAuth(targetProvider: 'google' | 'github') {
    setErrorMsg(null)
    const url = supabaseUrl.trim()
    const key = anonKey.trim()

    if (!url || !key) {
      setErrorMsg('Please enter both your Supabase Project URL and Anon API Key.')
      return
    }

    if (!url.startsWith('https://') || !url.includes('.supabase.co')) {
      setErrorMsg('Please enter a valid Supabase URL (e.g. https://your-project.supabase.co).')
      return
    }

    setIsLoading(true)
    saveSupabaseConfig(url, key)

    try {
      const res = await signInWithSupabaseOAuth(targetProvider, { url, anonKey: key })

      if (res.error) {
        setErrorMsg(res.error)
        setIsLoading(false)
        return
      }

      // If redirected, browser will navigate to Supabase -> Google/GitHub OAuth page
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to start Supabase OAuth.')
      setIsLoading(false)
    }
  }

  function handleDemoSignIn(e: React.FormEvent) {
    e.preventDefault()
    setErrorMsg(null)

    const email = customEmail.trim()
    if (!email || !email.includes('@')) {
      setErrorMsg('Please enter a valid email address.')
      return
    }

    const name =
      customName.trim() ||
      email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())

    const user: UserSession = {
      id: `${provider}_${Date.now()}`,
      name,
      email,
      image:
        provider === 'google'
          ? `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(name)}&backgroundColor=4285F4`
          : `https://avatars.githubusercontent.com/u/9919?v=4`,
      provider,
    }

    onSuccess(user)
    onClose()
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="supabase-auth-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200"
    >
      <div
        className="relative w-full max-w-md rounded-2xl border border-border/80 bg-card p-6 shadow-2xl text-card-foreground overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Glow */}
        <div className="pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 size-48 rounded-full bg-emerald-500/15 blur-3xl" />

        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close dialog"
          className="absolute top-4 right-4 grid size-8 place-items-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" />
        </button>

        {/* Header */}
        <div className="flex flex-col items-center text-center">
          <div className="flex items-center gap-2">
            <span className="grid size-11 place-items-center rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 shadow-sm">
              <Database className="size-5" />
            </span>
            <span className="text-muted-foreground text-xs font-semibold">+</span>
            <span className="grid size-11 place-items-center rounded-2xl bg-white shadow-sm border border-zinc-200 dark:border-zinc-800">
              {isGoogle ? <GoogleIcon className="size-5" /> : <GitHubIcon className="size-5" />}
            </span>
          </div>

          <h2 id="supabase-auth-title" className="mt-3 text-lg font-bold tracking-tight">
            Supabase {isGoogle ? 'Google' : 'GitHub'} OAuth
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Authenticate using your Supabase project with {isGoogle ? 'Google' : 'GitHub'} OAuth
          </p>
        </div>

        {/* Tab Toggle */}
        <div className="mt-5 grid grid-cols-2 rounded-xl bg-muted/50 p-1 border border-border/60 text-xs font-medium">
          <button
            type="button"
            onClick={() => { setActiveTab('supabase'); setErrorMsg(null); }}
            className={`py-2 rounded-lg transition-all ${
              activeTab === 'supabase'
                ? 'bg-background text-foreground shadow-sm font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Connect Supabase
          </button>
          <button
            type="button"
            onClick={() => { setActiveTab('demo'); setErrorMsg(null); }}
            className={`py-2 rounded-lg transition-all ${
              activeTab === 'demo'
                ? 'bg-background text-foreground shadow-sm font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Instant Test Login
          </button>
        </div>

        {errorMsg && (
          <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
            <AlertCircle className="size-4 shrink-0 mt-0.5" />
            <span className="leading-snug">{errorMsg}</span>
          </div>
        )}

        {/* Tab 1: Live Supabase OAuth */}
        {activeTab === 'supabase' && (
          <div className="mt-4 space-y-3.5">
            <div className="rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
              <p>
                Enter your Supabase credentials to trigger the live{' '}
                <strong className="text-foreground">{isGoogle ? 'Google' : 'GitHub'}</strong> OAuth
                consent screen via Supabase.
              </p>
            </div>

            <div>
              <label htmlFor="sb-url" className="block text-xs font-medium text-foreground mb-1">
                Supabase URL
              </label>
              <Input
                id="sb-url"
                value={supabaseUrl}
                onChange={(e) => setSupabaseUrl(e.target.value)}
                placeholder="https://your-project.supabase.co"
                className="font-mono text-xs h-9"
              />
            </div>

            <div>
              <label htmlFor="sb-key" className="block text-xs font-medium text-foreground mb-1">
                Supabase Anon Public Key
              </label>
              <Input
                id="sb-key"
                type="password"
                value={anonKey}
                onChange={(e) => setAnonKey(e.target.value)}
                placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                className="font-mono text-xs h-9"
              />
            </div>

            <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1">
              <a
                href="https://supabase.com/dashboard/project/_/settings/api"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-primary hover:underline font-medium"
              >
                Get Keys from Supabase Dashboard
                <ExternalLink className="size-3" />
              </a>
              <span className="text-[10px]">Saved in browser</span>
            </div>

            <div className="grid grid-cols-2 gap-2 pt-2">
              <Button
                type="button"
                className="w-full gap-2 text-xs font-semibold shadow-md"
                onClick={() => handleLaunchOAuth('google')}
                disabled={isLoading}
              >
                {isLoading && isGoogle ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <GoogleIcon className="size-4" />
                )}
                <span>Sign in with Google</span>
              </Button>

              <Button
                type="button"
                variant="outline"
                className="w-full gap-2 text-xs font-semibold shadow-md border-border/80"
                onClick={() => handleLaunchOAuth('github')}
                disabled={isLoading}
              >
                {isLoading && !isGoogle ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <GitHubIcon className="size-4" />
                )}
                <span>Sign in with GitHub</span>
              </Button>
            </div>
          </div>
        )}

        {/* Tab 2: Instant Test Login */}
        {activeTab === 'demo' && (
          <form onSubmit={handleDemoSignIn} className="mt-4 space-y-3.5">
            <div className="rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
              <div className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
                <Sparkles className="size-3.5 text-primary" />
                <span>One-Click Test Account</span>
              </div>
              <p>
                Test your workspace immediately with custom {isGoogle ? 'Google' : 'GitHub'} credentials
                while setting up Supabase.
              </p>
            </div>

            <div>
              <label htmlFor="test-email" className="block text-xs font-medium text-foreground mb-1">
                Your Email
              </label>
              <Input
                id="test-email"
                type="email"
                value={customEmail}
                onChange={(e) => setCustomEmail(e.target.value)}
                placeholder={isGoogle ? 'operator@gmail.com' : 'developer@github.com'}
                required
                className="text-xs h-9"
              />
            </div>

            <div>
              <label htmlFor="test-name" className="block text-xs font-medium text-foreground mb-1">
                Display Name (Optional)
              </label>
              <Input
                id="test-name"
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                placeholder="CHAI Operator"
                className="text-xs h-9"
              />
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full gap-2 text-xs font-semibold shadow-md mt-2"
            >
              <ShieldCheck className="size-4" />
              <span>Continue as {isGoogle ? 'Google' : 'GitHub'} Operator</span>
            </Button>
          </form>
        )}
      </div>
    </div>
  )
}
