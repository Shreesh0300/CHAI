"use client"

import type { ReactNode } from "react"
import { ArrowUpRight, MessageCircle, Search, Sparkles, Workflow } from "lucide-react"
import type { PromptSuggestion } from "@/components/chat-types"

interface ChatHeroProps {
  suggestions: PromptSuggestion[]
  onChoose: (suggestion: PromptSuggestion) => void
  composer: ReactNode
}

export function ChatHero({ suggestions, onChoose, composer }: ChatHeroProps) {
  return (
    <div className="relative flex min-h-0 flex-1 flex-col items-center justify-center px-1 py-6 text-center sm:min-h-[500px] sm:py-10">
      <div
        aria-hidden="true"
        className="chai-hero-aura pointer-events-none absolute left-1/2 top-8 -z-10 h-64 w-[min(90%,620px)] -translate-x-1/2 rounded-full blur-2xl"
      />

      <div className="mb-3 flex items-center gap-2 rounded-full border border-primary/15 bg-primary/5 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.17em] text-primary sm:mb-5">
        <Sparkles aria-hidden="true" className="size-3.5" />
        A thoughtful space to start
      </div>
      <h1 className="max-w-[680px] text-balance text-[clamp(1.9rem,7.5vw,2.4rem)] font-semibold leading-[1.06] tracking-[-0.055em] text-foreground sm:text-[3.45rem] sm:leading-[1.08]">
        Think it through.
        <br className="hidden sm:block" />
        Then make it happen.
      </h1>
      <p className="mt-3 max-w-[510px] text-pretty text-[13px] leading-5 text-muted-foreground sm:mt-4 sm:text-base sm:leading-7">
        Ask a quick question, explore an idea, or give a project room to unfold.
        Simple answers stay in chat; deeper work gets its own space.
      </p>

      <div className="mt-5 w-full max-w-[840px] text-left sm:mt-8">{composer}</div>

      <div className="mt-6 grid w-full max-w-[840px] grid-cols-1 gap-3 text-left sm:mt-9 sm:grid-cols-3 sm:gap-3.5">
        {suggestions.map((suggestion) => {
          const Icon =
            suggestion.mode === "ask"
              ? MessageCircle
              : suggestion.mode === "research"
                ? Search
                : Workflow

          return (
            <button
              key={suggestion.label}
              type="button"
              onClick={() => onChoose(suggestion)}
              className="group flex min-h-[86px] items-start gap-3 rounded-2xl border border-border/80 bg-card/90 p-3 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background sm:min-h-[94px] sm:p-4"
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-muted text-primary transition group-hover:bg-primary/10">
                <Icon aria-hidden="true" className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium leading-5 text-foreground">
                  {suggestion.label}
                </span>
                <span className="mt-1 block text-xs text-muted-foreground">
                  {suggestion.detail}
                </span>
              </span>
              <ArrowUpRight
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0 text-muted-foreground/70 transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-primary"
              />
            </button>
          )
        })}
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[10px] text-muted-foreground sm:mt-8 sm:text-[11px]">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
          Start with a plain question
        </span>
        <span className="hidden h-3 w-px bg-border sm:block" aria-hidden="true" />
        <span>Switch to Research or Agent when you need more</span>
      </div>
    </div>
  )
}
