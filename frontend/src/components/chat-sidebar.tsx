"use client"

import { useEffect, useMemo, useRef, useState, type RefObject } from "react"
import { MessageCircle, Search, X, Sparkles, Clock, FolderGit2 } from "lucide-react"
import type { AssistantMode, WorkspaceLayout } from "@/components/chat-types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { API_BASE } from "@/lib/api-config"

export interface SampleConversation {
  id: string
  title: string
  mode: AssistantMode
  layout: WorkspaceLayout
  prompt: string
  answer?: string
}

export const SAMPLE_CONVERSATIONS: SampleConversation[] = [
  {
    id: "onboarding",
    title: "A better onboarding flow",
    mode: "ask",
    layout: "chat",
    prompt: "What makes a good first-run experience for a new user?",
    answer:
      "A good first-run experience helps someone reach a meaningful win quickly. Show one clear next step, explain why it matters, and avoid asking for information before it is useful. Keep the path easy to skip or revisit, then use early behavior to make the next visit feel more relevant.",
  },
  {
    id: "comparison",
    title: "Campaign performance snapshot",
    mode: "research",
    layout: "workspace",
    prompt: "Review this campaign performance snapshot with a trend chart, channel breakdown, and next steps.",
  },
  {
    id: "launch",
    title: "Growth action brief",
    mode: "agent",
    layout: "workspace",
    prompt: "Create a growth action plan from this campaign performance snapshot, with milestones and measures of success.",
  },
]

interface ChatHistoryPopoverProps {
  open: boolean
  currentTitle: string
  activeHistoryId: string | null
  triggerRef: RefObject<HTMLButtonElement | null>
  onOpenSample: (sample: SampleConversation) => void
  onReturnToCurrent: () => void
  onClose: () => void
}

export function ChatHistoryPopover({
  open,
  currentTitle,
  activeHistoryId,
  triggerRef,
  onOpenSample,
  onReturnToCurrent,
  onClose,
}: ChatHistoryPopoverProps) {
  const [searchTerm, setSearchTerm] = useState("")
  const [remoteHistory, setRemoteHistory] = useState<SampleConversation[]>([])
  const popoverRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  // Fetch backend history data
  useEffect(() => {
    if (open) {
      fetch(`${API_BASE}/api/history`)
        .then((res) => (res.ok ? res.json() : []))
        .then((data: any[]) => {
          if (Array.isArray(data) && data.length > 0) {
            const formatted = data.map((d) => ({
              id: d.id,
              title: d.title,
              mode: (d.mode || "ask") as AssistantMode,
              layout: (d.layout || "chat") as WorkspaceLayout,
              prompt: d.messages?.[0]?.content || d.title,
              answer: d.messages?.[1]?.content,
            }))
            setRemoteHistory(formatted)
          }
        })
        .catch(() => {
          // offline or fallback to repo samples
        })
    }
  }, [open])

  const recentItems = useMemo(() => {
    const current =
      currentTitle && currentTitle !== "New chat"
        ? [{ id: "current", title: currentTitle, current: true as const, sample: null, isGitRepo: false }]
        : []

    // Combine git repository samples + any backend conversations
    const repoSamples = SAMPLE_CONVERSATIONS.map((sample) => ({
      id: sample.id,
      title: sample.title,
      current: false as const,
      sample,
      isGitRepo: true,
    }))

    const remoteItems = remoteHistory
      .filter((r) => !SAMPLE_CONVERSATIONS.some((s) => s.id === r.id))
      .map((item) => ({
        id: item.id,
        title: item.title,
        current: false as const,
        sample: item,
        isGitRepo: false,
      }))

    const all = [...current, ...repoSamples, ...remoteItems]
    const query = searchTerm.trim().toLowerCase()
    return all.filter((item) => item.title.toLowerCase().includes(query))
  }, [currentTitle, searchTerm, remoteHistory])

  useEffect(() => {
    if (!open) return

    const focusFrame = window.requestAnimationFrame(() => searchRef.current?.focus())
    const handlePointerDown = (event: PointerEvent) => {
      if (!(event.target instanceof Node)) return
      if (popoverRef.current?.contains(event.target)) return
      if (triggerRef.current?.contains(event.target)) return
      onClose()
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return
      onClose()
      window.requestAnimationFrame(() => triggerRef.current?.focus())
    }

    document.addEventListener("pointerdown", handlePointerDown)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      window.cancelAnimationFrame(focusFrame)
      document.removeEventListener("pointerdown", handlePointerDown)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [onClose, open, triggerRef])

  function selectConversation(item: (typeof recentItems)[number]) {
    if (item.current) {
      onReturnToCurrent()
    } else if (item.sample) {
      onOpenSample(item.sample)
    }
    onClose()
    window.requestAnimationFrame(() => triggerRef.current?.focus())
  }

  return (
    <div
      id="chat-history-popover"
      ref={popoverRef}
      role="dialog"
      aria-label="Conversation history"
      hidden={!open}
      className="absolute left-3 top-[56px] z-50 flex max-h-[min(80dvh,540px)] w-[min(380px,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-border/80 bg-popover text-popover-foreground shadow-2xl backdrop-blur-md"
    >
      <div className="flex items-center justify-between border-b border-border/70 px-4 py-3 bg-muted/20">
        <div className="flex items-center gap-2">
          <Clock className="size-4 text-primary" />
          <h2 className="text-xs font-bold tracking-tight">Conversation History</h2>
        </div>
        <button
          type="button"
          aria-label="Close conversation history"
          onClick={onClose}
          className="grid size-7 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      </div>

      <div className="p-3 border-b border-border/60">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            ref={searchRef}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.currentTarget.value)}
            placeholder="Search conversations..."
            className="h-8 pl-8 text-xs bg-background/80"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center justify-between">
          <span>Recent & Git Repo Threads</span>
          <span className="text-[9px] font-normal lowercase">{recentItems.length} items</span>
        </p>

        <div className="mt-1 flex flex-col gap-1">
          {recentItems.length === 0 ? (
            <p className="px-3 py-6 text-center text-xs text-muted-foreground">
              No conversations found.
            </p>
          ) : (
            recentItems.map((item) => {
              const isSelected = item.current
                ? activeHistoryId === "current"
                : activeHistoryId === item.id

              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => selectConversation(item)}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-xs transition",
                    isSelected
                      ? "bg-primary/10 text-primary font-medium"
                      : "hover:bg-muted/80 text-foreground",
                  )}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <MessageCircle className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{item.title}</span>
                  </div>

                  {item.isGitRepo && (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
                      <FolderGit2 className="size-2.5" />
                      Repo
                    </span>
                  )}
                  {item.current && (
                    <span className="shrink-0 text-[10px] text-primary font-medium">Active</span>
                  )}
                </button>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
