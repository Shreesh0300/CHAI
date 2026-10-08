'use client'

import { type FormEvent, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { LoaderCircle, Sparkles, UserRound } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldSeparator,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { authClient } from '@/lib/auth-client'
import { GoogleIcon, GitHubIcon } from '@/components/auth-icons'
import { SupabaseAuthModal } from '@/components/supabase-auth-modal'
import { signInWithSupabaseOAuth } from '@/lib/supabase'

export type AuthMode = 'sign-in' | 'sign-up'

type AuthFormProps = {
  mode: AuthMode
  variant?: 'page' | 'cover'
  onBack?: () => void
  onModeChange?: (mode: AuthMode) => void
}

export function AuthForm({
  mode,
  variant = 'page',
  onBack,
  onModeChange,
}: AuthFormProps) {
  const router = useRouter()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [socialLoading, setSocialLoading] = useState<'google' | 'github' | null>(null)
  const [showSupabaseModal, setShowSupabaseModal] = useState(false)
  const [supabaseProvider, setSupabaseProvider] = useState<'google' | 'github'>('google')
  const isSignUp = mode === 'sign-up'
  const isCover = variant === 'cover'

  async function handleSocialAuth(provider: 'google' | 'github') {
    setError(null)
    setSocialLoading(provider)

    try {
      const { error: sbError, redirected, needsConfig } = await signInWithSupabaseOAuth(provider)

      if (redirected) {
        return
      }

      if (needsConfig) {
        setSupabaseProvider(provider)
        setShowSupabaseModal(true)
        return
      }

      if (sbError) {
        setError(sbError)
        setSupabaseProvider(provider)
        setShowSupabaseModal(true)
        return
      }
    } catch {
      setSupabaseProvider(provider)
      setShowSupabaseModal(true)
    } finally {
      setSocialLoading(null)
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      const result = isSignUp
        ? await authClient.signUp.email({
            email: email.trim(),
            password,
            name: name.trim(),
          })
        : await authClient.signIn.email({
            email: email.trim(),
            password,
          })

      if (result.error) {
        setError('We couldn’t complete that request. Check your details and try again.')
        return
      }

      if (result.data) {
        window.dispatchEvent(new CustomEvent('chai-auth-change', { detail: result.data }))
      }
      router.replace('/workspace')
    } catch {
      setError('We couldn’t complete that request. Check your details and try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  function handleGuestContinue() {
    const guestUser = authClient.signInAsGuest()
    window.dispatchEvent(new CustomEvent('chai-auth-change', { detail: guestUser }))
    router.replace('/guest')
  }

  const authPanel = (
    <div className="relative mx-auto w-full max-w-[420px]">
      <div
        aria-hidden="true"
        className={cn(
          'chai-hero-aura pointer-events-none absolute rounded-full blur-3xl',
          isCover
            ? '-inset-x-12 -top-16 h-[440px] opacity-50'
            : '-inset-x-20 -top-40 h-[520px] opacity-70',
        )}
      />

      {!isCover && (
        <div className="mb-7 flex flex-col items-center text-center">
          <span className="mb-3 grid size-11 place-items-center rounded-2xl border border-border/70 bg-card/80 text-primary shadow-sm">
            <Sparkles aria-hidden="true" className="size-5" />
          </span>
          <p className="text-lg font-semibold tracking-tight">CHAI</p>
          <p className="mt-1 text-xs text-muted-foreground">Autonomous Framework</p>
        </div>
      )}

      <Card className="rgb-border chai-auth-glass border-0 py-0 shadow-[0_24px_80px_-28px_rgba(0,0,0,0.35)]">
        <CardHeader className="gap-2 px-6 pt-7 pb-0">
          <div className="flex items-center justify-between">
            <span className="w-fit rounded-full border border-border/70 bg-muted/50 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              {isSignUp ? 'Create Workspace' : 'Authentication'}
            </span>
            <span className="text-[10px] text-muted-foreground/80 font-mono">v2.4-hybrid</span>
          </div>
          <CardTitle
            role="heading"
            aria-level={1}
            className="pt-1 text-2xl font-semibold tracking-tight"
          >
            {isSignUp
              ? 'Create your CHAI account'
              : isCover
                ? 'Welcome back'
                : 'Welcome back to CHAI'}
          </CardTitle>
          <CardDescription className="text-sm leading-6">
            {isSignUp
              ? 'Choose your sign-in method to set up your workspace.'
              : 'Sign in to return to your workspace.'}
          </CardDescription>
        </CardHeader>

        <CardContent className="px-6 pt-5 pb-6">
          {/* Social Auth Buttons */}
          <div className="flex flex-col gap-2.5">
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="relative w-full justify-center gap-3 border-border/80 bg-background/60 hover:bg-muted font-medium text-xs sm:text-sm transition-all hover:border-primary/40 hover:shadow-[0_0_15px_-3px_rgba(66,133,244,0.2)]"
              onClick={() => handleSocialAuth('google')}
              disabled={isSubmitting || socialLoading !== null}
            >
              {socialLoading === 'google' ? (
                <LoaderCircle className="size-4 animate-spin text-primary" />
              ) : (
                <GoogleIcon className="size-4 shrink-0" />
              )}
              <span>Continue with Google</span>
            </Button>

            <Button
              type="button"
              variant="outline"
              size="lg"
              className="relative w-full justify-center gap-3 border-border/80 bg-background/60 hover:bg-muted font-medium text-xs sm:text-sm transition-all hover:border-primary/40 hover:shadow-[0_0_15px_-3px_rgba(255,255,255,0.12)]"
              onClick={() => handleSocialAuth('github')}
              disabled={isSubmitting || socialLoading !== null}
            >
              {socialLoading === 'github' ? (
                <LoaderCircle className="size-4 animate-spin text-primary" />
              ) : (
                <GitHubIcon className="size-4 shrink-0" />
              )}
              <span>Continue with GitHub</span>
            </Button>
          </div>

          <FieldSeparator className="my-5 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
            Or continue with email
          </FieldSeparator>

          <form
            onSubmit={handleSubmit}
            aria-busy={isSubmitting}
            aria-describedby={error ? 'auth-form-error' : undefined}
          >
            <FieldGroup className="gap-4">
              {isSignUp && (
                <Field>
                  <FieldLabel htmlFor="auth-name">Name</FieldLabel>
                  <Input
                    id="auth-name"
                    value={name}
                    onChange={(event) => setName(event.currentTarget.value)}
                    autoComplete="name"
                    maxLength={48}
                    required
                  />
                </Field>
              )}

              <Field>
                <FieldLabel htmlFor="auth-email">Email</FieldLabel>
                <Input
                  id="auth-email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.currentTarget.value)}
                  autoComplete="email"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="auth-password">Password</FieldLabel>
                <Input
                  id="auth-password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.currentTarget.value)}
                  autoComplete={isSignUp ? 'new-password' : 'current-password'}
                  minLength={8}
                  maxLength={128}
                  required
                />
                {isSignUp && (
                  <FieldDescription>Use 8 to 128 characters.</FieldDescription>
                )}
              </Field>
            </FieldGroup>

            {error && (
              <FieldError id="auth-form-error" className="mt-4">
                {error}
              </FieldError>
            )}

            <Button
              type="submit"
              size="lg"
              className="mt-5 w-full shadow-md"
              disabled={isSubmitting || socialLoading !== null}
            >
              {isSubmitting && (
                <LoaderCircle
                  aria-hidden="true"
                  data-icon="inline-start"
                  className="animate-spin"
                />
              )}
              {isSubmitting
                ? isSignUp
                  ? 'Creating account…'
                  : 'Signing in…'
                : isSignUp
                  ? 'Create account'
                  : isCover
                    ? 'Access Portal'
                    : 'Sign in'}
            </Button>
          </form>

          {/* Guest Access Option - Preserved & Distinct */}
          <div className="mt-4 pt-1">
            <FieldSeparator className="my-3.5 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
              Or continue as guest
            </FieldSeparator>
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="w-full gap-2 border-dashed border-border/80 bg-background/30 hover:bg-muted/70 text-xs sm:text-sm font-medium transition-all"
              onClick={handleGuestContinue}
              disabled={isSubmitting || socialLoading !== null}
            >
              <UserRound aria-hidden="true" className="size-4 text-muted-foreground" />
              <span>Continue as guest</span>
            </Button>
          </div>
        </CardContent>

        <CardFooter
          className={cn(
            'justify-center px-6 py-4 text-center',
            isCover && 'flex-col gap-3',
          )}
        >
          <p className="text-xs text-muted-foreground">
            {isSignUp ? 'Already have an account?' : 'New to CHAI?'}{' '}
            {onModeChange ? (
              <button
                type="button"
                onClick={() => onModeChange(isSignUp ? 'sign-in' : 'sign-up')}
                className="font-medium text-foreground underline-offset-4 transition hover:underline"
              >
                {isSignUp ? 'Sign in' : 'Create an account'}
              </button>
            ) : (
              <Link
                href={isSignUp ? '/sign-in' : '/sign-up'}
                className="font-medium text-foreground underline-offset-4 transition hover:underline"
              >
                {isSignUp ? 'Sign in' : 'Create an account'}
              </Link>
            )}
          </p>
          {onBack && (
            <Button
              type="button"
              variant="ghost"
              size="lg"
              onClick={onBack}
              className="w-full"
            >
              ← Back
            </Button>
          )}
        </CardFooter>
      </Card>

      {!isCover && (
        <p className="mt-5 text-center text-[11px] leading-5 text-muted-foreground">
          Your CHAI account keeps your workspace private and ready when you return.
        </p>
      )}

      <SupabaseAuthModal
        isOpen={showSupabaseModal}
        provider={supabaseProvider}
        onClose={() => setShowSupabaseModal(false)}
        onSuccess={(user) => {
          window.dispatchEvent(new CustomEvent('chai-auth-change', { detail: user }))
          router.replace('/workspace')
        }}
      />
    </div>
  )

  if (isCover) return <div className="w-full px-1 sm:px-0">{authPanel}</div>

  return (
    <main className="relative flex min-h-svh items-center justify-center overflow-hidden bg-background px-4 py-12 sm:px-6">
      {authPanel}
    </main>
  )
}
