"use client"

import { type FormEvent, useEffect, useRef, useState } from "react"
import {
  Check,
  ChevronDown,
  LoaderCircle,
  LogOut,
  Moon,
  Sparkles,
  Sun,
  User,
  UserCheck,
  UserRound,
  X,
  ShieldCheck,
  Cpu,
} from "lucide-react"
import { useRouter } from "next/navigation"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { authClient } from "@/lib/auth-client"
import { GoogleIcon, GitHubIcon } from "@/components/auth-icons"
import { SupabaseAuthModal } from "@/components/supabase-auth-modal"
import { signInWithSupabaseOAuth } from "@/lib/supabase"
import { cn } from "@/lib/utils"

type ThemeChoice = "system" | "light" | "dark"
type AccentChoice = "violet" | "blue" | "teal" | "rose" | "amber"

export type ProfileMenuUser = {
  id?: string
  name: string
  email: string
  image?: string | null
  provider?: 'email' | 'google' | 'github' | 'guest'
}

const ACCENTS: Record<AccentChoice, { label: string; swatch: string; light: string; dark: string }> = {
  violet: {
    label: "Violet",
    swatch: "#7064e8",
    light: "oklch(0.51 0.18 277)",
    dark: "oklch(0.74 0.13 277)",
  },
  blue: {
    label: "Blue",
    swatch: "#3979df",
    light: "oklch(0.51 0.17 255)",
    dark: "oklch(0.74 0.13 255)",
  },
  teal: {
    label: "Teal",
    swatch: "#148b7e",
    light: "oklch(0.5 0.13 188)",
    dark: "oklch(0.75 0.12 190)",
  },
  rose: {
    label: "Rose",
    swatch: "#ce5478",
    light: "oklch(0.5 0.17 8)",
    dark: "oklch(0.73 0.14 8)",
  },
  amber: {
    label: "Amber",
    swatch: "#a96a09",
    light: "oklch(0.56 0.15 73)",
    dark: "oklch(0.8 0.12 79)",
  },
}

function getInitials(name: string) {
  return name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase()
}

export function ProfileMenu({ user }: { user: ProfileMenuUser | null }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState<ThemeChoice>(() => {
    if (typeof window === "undefined") return "dark"
    return (localStorage.getItem("chai-theme") as ThemeChoice) || "dark"
  })
  const [accent, setAccent] = useState<AccentChoice>(() => {
    if (typeof window === "undefined") return "violet"
    return (localStorage.getItem("chai-accent") as AccentChoice) || "violet"
  })
  const [displayName, setDisplayName] = useState(user?.name || "CHAI Operator")
  const [draftName, setDraftName] = useState(user?.name || "CHAI Operator")
  const [editingProfile, setEditingProfile] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [isSavingProfile, setIsSavingProfile] = useState(false)
  const [isSigningOut, setIsSigningOut] = useState(false)
  const [linkingProvider, setLinkingProvider] = useState<'google' | 'github' | null>(null)
  const [showSupabaseModal, setShowSupabaseModal] = useState(false)
  const [supabaseProvider, setSupabaseProvider] = useState<'google' | 'github'>('google')

  const triggerRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (user?.name) {
      setDisplayName(user.name)
      setDraftName(user.name)
    }
  }, [user])

  useEffect(() => {
    const root = document.documentElement
    const isDark = theme !== "light"
    root.classList.toggle("dark", isDark)
    root.classList.toggle("light", !isDark)
    localStorage.setItem("chai-theme", isDark ? "dark" : "light")
    window.dispatchEvent(new CustomEvent("chai-theme-change", { detail: isDark ? "dark" : "light" }))
  }, [theme])

  useEffect(() => {
    const root = document.documentElement
    const selectedAccent = ACCENTS[accent]
    root.style.setProperty("--profile-accent-color", selectedAccent.swatch)
    root.style.setProperty("--profile-accent-light", selectedAccent.light)
    root.style.setProperty("--profile-accent-dark", selectedAccent.dark)
    localStorage.setItem("chai-accent", accent)
    localStorage.setItem("chai-accent-color", selectedAccent.swatch)
    window.dispatchEvent(new CustomEvent("chai-accent-change", { detail: accent }))
  }, [accent])

  // Sync external accent changes (e.g. from voice assistant)
  useEffect(() => {
    const handleExternalAccent = (e: Event) => {
      const custom = e as CustomEvent<string>
      if (custom.detail && (custom.detail in ACCENTS)) {
        setAccent(custom.detail as AccentChoice)
      }
    }
    window.addEventListener("chai-accent-change", handleExternalAccent as EventListener)
    return () => window.removeEventListener("chai-accent-change", handleExternalAccent as EventListener)
  }, [])

  useEffect(() => {
    if (!open) return

    const focusFrame = window.requestAnimationFrame(() => closeButtonRef.current?.focus())
    const handlePointerDown = (event: PointerEvent) => {
      if (!(event.target instanceof Node)) return
      if (popoverRef.current?.contains(event.target)) return
      if (triggerRef.current?.contains(event.target)) return
      setOpen(false)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return
      setOpen(false)
      window.requestAnimationFrame(() => triggerRef.current?.focus())
    }

    document.addEventListener("pointerdown", handlePointerDown)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      window.cancelAnimationFrame(focusFrame)
      document.removeEventListener("pointerdown", handlePointerDown)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [open])

  function startEditingProfile() {
    setProfileError(null)
    setDraftName(displayName)
    setEditingProfile(true)
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextName = draftName.trim()
    if (!nextName) return
    if (nextName === displayName) {
      setEditingProfile(false)
      return
    }

    setProfileError(null)
    setIsSavingProfile(true)

    try {
      const { error } = await authClient.updateUser({ name: nextName })
      if (error) {
        setProfileError("Could not update profile. Please try again.")
        return
      }

      setDisplayName(nextName)
      setEditingProfile(false)
      window.dispatchEvent(new CustomEvent('chai-auth-change', {
        detail: {
          ...user,
          name: nextName,
          email: user?.email || '',
        }
      }))
    } catch {
      setProfileError("Could not update profile. Please try again.")
    } finally {
      setIsSavingProfile(false)
    }
  }

  async function handleLinkSocial(provider: 'google' | 'github') {
    setProfileError(null)
    setLinkingProvider(provider)

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
        setProfileError(sbError)
        setSupabaseProvider(provider)
        setShowSupabaseModal(true)
        return
      }
    } catch {
      setSupabaseProvider(provider)
      setShowSupabaseModal(true)
    } finally {
      setLinkingProvider(null)
    }
  }

  async function handleSignOut() {
    setProfileError(null)
    setIsSigningOut(true)

    try {
      await authClient.signOut()
      setOpen(false)
      // Signal auth change to App.tsx
      window.dispatchEvent(new CustomEvent('chai-auth-change', { detail: null }))
      router.replace("/")
    } catch {
      setProfileError("Could not sign out. Please try again.")
    } finally {
      setIsSigningOut(false)
    }
  }

  const isGuest = user?.provider === 'guest' || !user

  return (
    <div className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        aria-label="User Profile and Settings"
        title="User Profile and Settings"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="profile-settings-popover"
        onClick={() => setOpen((current) => !current)}
        className={cn(
          "inline-flex h-9 items-center justify-center gap-2 rounded-full border border-border/80 bg-background/80 px-2.5 text-xs font-medium text-foreground transition hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:pr-3",
          open && "bg-muted border-primary/40 ring-2 ring-primary/20",
        )}
      >
        <span className="relative grid size-6 place-items-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground overflow-hidden">
          {user?.image ? (
            <img
              src={user.image}
              alt={displayName}
              className="size-full object-cover"
              onError={(e) => {
                e.currentTarget.style.display = "none"
              }}
            />
          ) : user ? (
            getInitials(displayName) || getInitials(user.email.split("@")[0]) || "OP"
          ) : (
            <UserRound aria-hidden="true" className="size-3.5" />
          )}
          <span className="absolute -bottom-0.5 -right-0.5 size-2 rounded-full bg-emerald-500 ring-2 ring-background" />
        </span>
        <span className="font-semibold text-xs tracking-tight">Profile</span>
        <ChevronDown aria-hidden="true" className="size-3 text-muted-foreground" />
      </button>

      <div
        id="profile-settings-popover"
        ref={popoverRef}
        role="dialog"
        aria-label="User Profile"
        hidden={!open}
        className="absolute right-0 top-full z-50 mt-2 flex max-h-[min(85dvh,640px)] w-[min(380px,calc(100vw-1.5rem))] flex-col overflow-y-auto rounded-2xl border border-border/80 bg-popover text-popover-foreground shadow-2xl backdrop-blur-md"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-border/70 px-4 py-3.5 bg-muted/20">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold tracking-tight">User Profile</h2>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-500">
                <span className="size-1.5 rounded-full bg-emerald-500" />
                Active
              </span>
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              CHAI Intelligence Operator Account
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            aria-label="Close profile"
            onClick={() => {
              setOpen(false)
              window.requestAnimationFrame(() => triggerRef.current?.focus())
            }}
            className="grid size-7 shrink-0 place-items-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </div>

        {/* Profile Card Section */}
        <section className="px-4 py-4 border-b border-border/60">
          <div className="flex items-center gap-3.5">
            <div className="relative shrink-0">
              {user?.image ? (
                <img
                  src={user.image}
                  alt={displayName}
                  className="size-12 rounded-2xl object-cover ring-1 ring-primary/20 shadow-sm"
                  onError={(e) => {
                    e.currentTarget.style.display = "none"
                  }}
                />
              ) : (
                <span className="grid size-12 place-items-center rounded-2xl bg-gradient-to-tr from-primary/30 to-primary/10 text-base font-bold text-primary ring-1 ring-primary/20">
                  {getInitials(displayName) || (user ? getInitials(user.email.split("@")[0]) : "OP")}
                </span>
              )}
              <span className="absolute -bottom-1 -right-1 size-3.5 rounded-full bg-emerald-500 ring-2 ring-popover" />
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="truncate text-sm font-bold">{displayName}</p>
                <ShieldCheck className="size-4 text-primary shrink-0" />
              </div>
              <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                {user?.email || "guest@chai.ai"}
              </p>

              {/* Provider Badge */}
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {user?.provider === 'google' ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 text-[10px] font-semibold text-blue-400">
                    <GoogleIcon className="size-3" />
                    Google Account
                  </span>
                ) : user?.provider === 'github' ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-zinc-500/10 border border-zinc-500/20 px-2 py-0.5 text-[10px] font-semibold text-zinc-300">
                    <GitHubIcon className="size-3" />
                    GitHub Account
                  </span>
                ) : isGuest ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                    <UserRound className="size-3" />
                    Guest Operator
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                    <ShieldCheck className="size-3" />
                    Verified Member
                  </span>
                )}
                <span className="text-[10px] text-muted-foreground/80 font-mono">
                  #{(user?.id || user?.email || "guest").slice(0, 8)}
                </span>
              </div>
            </div>

            {!editingProfile && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={startEditingProfile}
                className="text-xs h-8 shrink-0"
              >
                Edit
              </Button>
            )}
          </div>

          {editingProfile && (
            <form onSubmit={saveProfile} className="mt-3 rounded-xl border border-border/80 bg-muted/30 p-3">
              <FieldGroup className="gap-2.5">
                <Field>
                  <FieldLabel htmlFor="profile-display-name" className="text-xs">Display Name</FieldLabel>
                  <Input
                    id="profile-display-name"
                    value={draftName}
                    onChange={(event) => setDraftName(event.currentTarget.value)}
                    maxLength={48}
                    autoFocus
                    required
                    className="h-8 text-xs"
                  />
                </Field>
                {profileError && <FieldError>{profileError}</FieldError>}
                <div className="flex justify-end gap-2 pt-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => {
                      setEditingProfile(false)
                      setProfileError(null)
                    }}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" className="h-7 text-xs" disabled={isSavingProfile}>
                    {isSavingProfile ? <LoaderCircle className="size-3 animate-spin" /> : "Save"}
                  </Button>
                </div>
              </FieldGroup>
            </form>
          )}

          {/* Quick Connect for Guest Users */}
          {isGuest && (
            <div className="mt-3 rounded-xl border border-border/80 bg-muted/20 p-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-foreground">Connect Account</span>
                <span className="text-[9px] text-muted-foreground uppercase tracking-wider font-mono">Sync Workspace</span>
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                Link Google or GitHub to retain your history &amp; preferences.
              </p>
              <div className="grid grid-cols-2 gap-2 mt-2.5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 text-[11px] gap-1.5 border-border/80 bg-background/60 hover:bg-muted"
                  onClick={() => handleLinkSocial('google')}
                  disabled={linkingProvider !== null}
                >
                  {linkingProvider === 'google' ? (
                    <LoaderCircle className="size-3 animate-spin text-primary" />
                  ) : (
                    <GoogleIcon className="size-3 shrink-0" />
                  )}
                  <span>Google</span>
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 text-[11px] gap-1.5 border-border/80 bg-background/60 hover:bg-muted"
                  onClick={() => handleLinkSocial('github')}
                  disabled={linkingProvider !== null}
                >
                  {linkingProvider === 'github' ? (
                    <LoaderCircle className="size-3 animate-spin text-primary" />
                  ) : (
                    <GitHubIcon className="size-3 shrink-0" />
                  )}
                  <span>GitHub</span>
                </Button>
              </div>
            </div>
          )}
        </section>

        {/* Intelligence Platform Status */}
        <section className="px-4 py-3.5 border-b border-border/60 bg-muted/10">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <Cpu className="size-3.5 text-primary" />
            Connected Agents
          </p>
          <div className="mt-2.5 grid grid-cols-2 gap-2 text-[11px]">
            <div className="rounded-lg border border-border/60 bg-background/60 p-2">
              <span className="text-muted-foreground block text-[10px]">Active Agents</span>
              <span className="font-semibold text-foreground">5 Core Agents</span>
            </div>
            <div className="rounded-lg border border-border/60 bg-background/60 p-2">
              <span className="text-muted-foreground block text-[10px]">Architecture</span>
              <span className="font-semibold text-foreground">Hybrid Orchestrator</span>
            </div>
          </div>
        </section>

        {/* Personalization */}
        <section className="px-4 py-3.5 border-b border-border/60">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            Appearance
          </p>

          <div className="flex items-center justify-between gap-3 text-xs mb-3">
            <span className="text-muted-foreground">Color Scheme</span>
            <ToggleGroup
              value={[theme]}
              onValueChange={(val) => {
                const next = val[0] as ThemeChoice
                if (next) setTheme(next)
              }}
              className="gap-0.5 rounded-lg border border-border p-0.5"
            >
              <ToggleGroupItem value="system" aria-label="System" className="h-6 px-2 text-[10px]">
                Auto
              </ToggleGroupItem>
              <ToggleGroupItem value="light" aria-label="Light" className="h-6 px-2 text-[10px]">
                <Sun className="size-3" />
              </ToggleGroupItem>
              <ToggleGroupItem value="dark" aria-label="Dark" className="h-6 px-2 text-[10px]">
                <Moon className="size-3" />
              </ToggleGroupItem>
            </ToggleGroup>
          </div>

          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="text-muted-foreground">Workspace Accent</span>
            <div className="flex items-center gap-1.5">
              {(Object.keys(ACCENTS) as AccentChoice[]).map((choice) => {
                const acc = ACCENTS[choice]
                const isActive = accent === choice
                return (
                  <button
                    key={choice}
                    type="button"
                    onClick={() => setAccent(choice)}
                    aria-label={`Accent ${acc.label}`}
                    style={{ backgroundColor: acc.swatch }}
                    className={cn(
                      "size-5 rounded-full transition-all",
                      isActive ? "ring-2 ring-primary ring-offset-2 ring-offset-popover scale-110" : "opacity-75 hover:opacity-100"
                    )}
                  />
                )
              })}
            </div>
          </div>
        </section>

        {/* Logout Action */}
        <div className="p-3 bg-muted/20 mt-auto">
          <Button
            type="button"
            variant="ghost"
            onClick={handleSignOut}
            disabled={isSigningOut}
            className="w-full justify-center gap-2 rounded-xl text-xs font-semibold text-red-600 hover:bg-red-500/10 hover:text-red-500 transition-colors h-9"
          >
            {isSigningOut ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <LogOut className="size-4" />
            )}
            <span>Log Out of CHAI</span>
          </Button>
        </div>
      </div>

      <SupabaseAuthModal
        isOpen={showSupabaseModal}
        provider={supabaseProvider}
        onClose={() => setShowSupabaseModal(false)}
        onSuccess={(newUser) => {
          window.dispatchEvent(new CustomEvent('chai-auth-change', { detail: newUser }))
        }}
      />
    </div>
  )
}
