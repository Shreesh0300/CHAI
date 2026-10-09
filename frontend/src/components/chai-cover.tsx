'use client'

import { useState, useEffect } from 'react'
import { ArrowDown, ArrowUpRight, Moon, MessageCircle, Search, Sparkles, Sun, Workflow } from 'lucide-react'
import { AuthForm, type AuthMode } from '@/components/auth-form'
import { CoverWorkspacePreview } from '@/components/cover-workspace-preview'
import { ParticleField } from '@/components/particle-field'
import { cn } from '@/lib/utils'

type CoverTheme = 'dark' | 'light'

const CAPABILITIES = [
  {
    number: '01',
    icon: MessageCircle,
    title: 'Quick answers, kept simple',
    description: 'Short questions stay in a clear, focused conversation without extra panels.',
  },
  {
    number: '02',
    icon: Search,
    title: 'Research with room to breathe',
    description: 'When a prompt needs more structure, results open on a canvas with chat alongside.',
  },
  {
    number: '03',
    icon: Workflow,
    title: 'Work you can keep refining',
    description: 'Follow up from the side panel while your plan, analysis, or deliverable stays in view.',
  },
]

export function ChaiCover() {
  const [theme, setTheme] = useState<CoverTheme>(() => {
    if (typeof window === 'undefined') return 'dark'
    return (localStorage.getItem('chai-theme') as CoverTheme) || 'dark'
  })
  const [authMode, setAuthMode] = useState<AuthMode | null>(null)

  useEffect(() => {
    const handleThemeChange = (e: Event) => {
      const custom = e as CustomEvent<CoverTheme>
      if (custom.detail) setTheme(custom.detail)
    }
    window.addEventListener('chai-theme-change', handleThemeChange as EventListener)
    return () => window.removeEventListener('chai-theme-change', handleThemeChange as EventListener)
  }, [])

  return (
    <main id="top" className="chai-cover relative isolate min-h-svh overflow-x-clip" data-theme={theme}>
      <section className="chai-cover__hero relative isolate flex min-h-svh flex-col">
        <ParticleField theme={theme} />

        <header className="relative z-10 mx-auto flex h-[72px] w-full max-w-7xl items-center justify-between gap-4 px-5 sm:px-8">
          <a href="#top" aria-label="CHAI home" className="flex shrink-0 items-center gap-2.5">
            <span className="chai-cover__brand-mark grid size-8 place-items-center rounded-xl">
              <Sparkles aria-hidden="true" className="size-4" />
            </span>
            <span className="text-[13px] font-semibold tracking-[0.2em]">CHAI</span>
          </a>

          {authMode === null && (
            <nav aria-label="Main navigation" className="hidden items-center gap-7 text-xs text-[var(--chai-muted)] md:flex">
              <a href="#how-it-works" className="transition hover:text-[var(--chai-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chai-foreground)]">
                How it works
              </a>
              <a href="#workspace-showcase" className="transition hover:text-[var(--chai-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chai-foreground)]">
                Workspace Showcase
              </a>
            </nav>
          )}

          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            {authMode === null && (
              <>
                <button
                  type="button"
                  onClick={() => setAuthMode('sign-in')}
                  className="inline-flex min-h-9 items-center rounded-full px-3.5 text-xs font-semibold text-[var(--chai-foreground)] bg-white/5 border border-[var(--chai-border)] transition hover:bg-white/10"
                >
                  Sign in
                </button>
                <button
                  type="button"
                  onClick={() => {
                    window.history.pushState({}, '', '/workspace')
                    window.dispatchEvent(new CustomEvent('chai-navigate', { detail: '/workspace' }))
                  }}
                  className="hidden sm:inline-flex min-h-9 items-center rounded-full px-3 text-xs font-medium text-[var(--chai-muted)] transition hover:text-[var(--chai-foreground)]"
                >
                  Workspace
                </button>
              </>
            )}
            <button
              type="button"
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              aria-pressed={theme === 'light'}
              onClick={() => {
                const next: CoverTheme = theme === 'dark' ? 'light' : 'dark'
                setTheme(next)
                localStorage.setItem('chai-theme', next)
                window.dispatchEvent(new CustomEvent('chai-theme-change', { detail: next }))
              }}
              className="inline-flex size-9 items-center justify-center rounded-full border border-[var(--chai-border)] text-[var(--chai-foreground)] transition hover:bg-[var(--chai-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chai-foreground)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--chai-background)] motion-reduce:transition-none"
            >
              {theme === 'dark' ? (
                <Sun aria-hidden="true" className="size-4" />
              ) : (
                <Moon aria-hidden="true" className="size-4" />
              )}
            </button>
          </div>
        </header>

        <div className="relative z-10 mx-auto grid w-full max-w-7xl flex-1 grid-cols-1 content-center px-5 py-10 sm:px-8 sm:py-12">
          {authMode === null ? (
            <section
              aria-label="CHAI introduction"
              className="grid w-full grid-cols-1 items-center gap-10 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-700 lg:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)] lg:gap-12 xl:gap-16"
            >
              <div className="mx-auto flex w-full max-w-[590px] flex-col items-center text-center lg:mx-0 lg:items-start lg:text-left">
                <span className="inline-flex items-center gap-2 rounded-full border border-[var(--chai-border)] bg-white/[0.035] px-3.5 py-1.5 text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--chai-muted)] sm:text-[11px]">
                  <span aria-hidden="true" className="chai-cover__signal size-1.5 rounded-full" />
                  Autonomous workspace
                </span>

                <h1 className="mt-6 text-balance text-[clamp(2.65rem,5.2vw,4.5rem)] font-semibold leading-[0.98] tracking-[-0.065em] sm:mt-8">
                  <span className="whitespace-nowrap">Think clearly.</span>
                  <br />
                  <span className="chai-gradient-text whitespace-nowrap">Work in sync.</span>
                </h1>

                <p className="mt-5 max-w-[490px] text-pretty text-sm leading-7 text-[var(--chai-muted)] sm:mt-6 sm:text-base sm:leading-8">
                  CHAI turns one clear prompt into coordinated, thoughtful work. Simple answers stay in chat; bigger ideas get a workspace of their own.
                </p>

                <div className="mt-7 flex w-full max-w-[480px] flex-col gap-3 sm:mt-8 sm:flex-row sm:gap-3 lg:justify-start">
                  <button
                    type="button"
                    onClick={() => setAuthMode('sign-in')}
                    className="chai-cover__primary-button inline-flex min-h-12 flex-1 items-center justify-center gap-2 rounded-full px-5 text-[13px] font-semibold transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chai-foreground)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--chai-background)] motion-reduce:transition-none"
                  >
                    Sign in
                    <ArrowUpRight aria-hidden="true" className="size-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setAuthMode('sign-up')}
                    className="chai-cover__secondary-button inline-flex min-h-12 flex-1 items-center justify-center rounded-full px-5 text-[13px] font-medium transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chai-foreground)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--chai-background)] motion-reduce:transition-none"
                  >
                    Sign Up
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      window.history.pushState({}, '', '/workspace')
                      window.dispatchEvent(new CustomEvent('chai-navigate', { detail: '/workspace' }))
                    }}
                    className="inline-flex min-h-12 items-center justify-center rounded-full px-4 text-[13px] font-medium text-[var(--chai-muted)] border border-[var(--chai-border)] bg-white/[0.02] hover:bg-white/5 hover:text-[var(--chai-foreground)] transition"
                  >
                    Guest Access
                  </button>
                </div>

                <div className="mt-7 flex flex-wrap items-center justify-center gap-2 lg:justify-start">
                  <span className="sr-only">Available modes:</span>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--chai-border)] bg-white/[0.025] px-3 py-1.5 text-[10px] text-[var(--chai-muted)]">
                    <MessageCircle aria-hidden="true" className="size-3 text-[#bba9ff]" />
                    Ask
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--chai-border)] bg-white/[0.025] px-3 py-1.5 text-[10px] text-[var(--chai-muted)]">
                    <Search aria-hidden="true" className="size-3 text-[#82d8f4]" />
                    Research
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--chai-border)] bg-white/[0.025] px-3 py-1.5 text-[10px] text-[var(--chai-muted)]">
                    <Workflow aria-hidden="true" className="size-3 text-[#d4a8ff]" />
                    Agent
                  </span>
                </div>
              </div>

              <div className="w-full lg:py-5">
                <CoverWorkspacePreview />
              </div>
            </section>
          ) : (
            <section
              aria-label="Access your CHAI workspace"
              className="mx-auto w-full max-w-[440px] motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-3 motion-safe:duration-500"
            >
              <AuthForm
                mode={authMode}
                variant="cover"
                onBack={() => setAuthMode(null)}
                onModeChange={setAuthMode}
              />
            </section>
          )}
        </div>

        {authMode === null && (
          <a
            href="#how-it-works"
            className="relative z-10 mx-auto mb-5 inline-flex items-center gap-2 rounded-full px-3 py-2 text-[10px] font-medium tracking-wide text-[var(--chai-muted)] transition hover:text-[var(--chai-foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chai-foreground)] motion-reduce:transition-none"
          >
            Explore the CHAI flow
            <ArrowDown aria-hidden="true" className="size-3.5" />
          </a>
        )}
      </section>

      {authMode === null && (
        <>
          <section
            id="how-it-works"
            aria-labelledby="how-it-works-heading"
            className="chai-cover__features relative z-10 mx-auto w-full max-w-7xl px-5 py-16 sm:px-8 sm:py-20 lg:py-24"
          >
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div className="max-w-[650px]">
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--chai-accent)]">
                  One prompt, the right workspace
                </p>
                <h2 id="how-it-works-heading" className="mt-3 text-balance text-3xl font-semibold tracking-[-0.055em] sm:text-4xl">
                  Let the work set the pace.
                </h2>
              </div>
              <p className="max-w-[400px] text-sm leading-6 text-[var(--chai-muted)]">
                Stay in a simple chat for quick answers. When the work grows, keep the result in view and the conversation close.
              </p>
            </div>

            <div className="mt-8 grid gap-3 sm:mt-10 md:grid-cols-3 md:gap-4">
              {CAPABILITIES.map((capability) => {
                const Icon = capability.icon

                return (
                  <article
                    key={capability.number}
                    className="chai-cover__feature-card group flex min-h-[205px] flex-col rounded-2xl p-5 transition duration-200 hover:-translate-y-1 sm:p-6 motion-reduce:transition-none"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="chai-cover__feature-icon grid size-10 place-items-center rounded-xl">
                        <Icon aria-hidden="true" className="size-4" />
                      </span>
                      <span className="text-[10px] font-medium tracking-[0.12em] text-[var(--chai-muted)]">
                        {capability.number}
                      </span>
                    </div>
                    <h3 className="mt-6 text-base font-semibold tracking-tight">
                      {capability.title}
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-[var(--chai-muted)]">
                      {capability.description}
                    </p>
                  </article>
                )
              })}
            </div>
          </section>

          <footer className="chai-cover__footer relative z-10 px-5 py-5 sm:px-8">
            <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3 text-[10px] text-[var(--chai-muted)]">
              <span className="font-semibold tracking-[0.18em] text-[var(--chai-foreground)]">CHAI</span>
              <span>A calmer way to coordinate ambitious work.</span>
            </div>
          </footer>
        </>
      )}
    </main>
  )
}
