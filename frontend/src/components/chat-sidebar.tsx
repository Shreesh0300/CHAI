"use client"

import { useEffect, useMemo, useRef, useState, type RefObject } from "react"
import { MessageCircle, Search, X, Sparkles, Clock, FolderGit2, Trash2, ArrowUpRight } from "lucide-react"
import type { AssistantMode, ChatMessage, WorkspaceLayout } from "@/components/chat-types"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { getApiBaseUrl } from "@/lib/api"
import { supabase } from "@/lib/supabase"

export interface SampleConversation {
  id: string
  title: string
  mode: AssistantMode
  layout: WorkspaceLayout
  prompt: string
  answer?: string
  messages?: ChatMessage[]
  createdAt?: string
  isGitRepo?: boolean
}

export const STARTER_CONVERSATIONS: SampleConversation[] = [
  {
    id: "starter_onboarding",
    title: "A better onboarding flow",
    mode: "ask",
    layout: "chat",
    prompt: "What makes a good first-run experience for a new user?",
    answer:
      "A good first-run experience helps someone reach a meaningful win quickly. Show one clear next step, explain why it matters, and avoid asking for information before it is useful. Keep the path easy to skip or revisit, then use early behavior to make the next visit feel more relevant.",
    isGitRepo: true,
  },
  {
    id: "starter_comparison",
    title: "Campaign performance snapshot",
    mode: "research",
    layout: "workspace",
    prompt: "Review this campaign performance snapshot with a trend chart, channel breakdown, and next steps.",
    isGitRepo: true,
  },
  {
    id: "starter_growth",
    title: "Growth action brief",
    mode: "agent",
    layout: "workspace",
    prompt: "Create a growth action plan from this campaign performance snapshot, with milestones and measures of success.",
    isGitRepo: true,
  },
]

export const SAMPLE_CONVERSATIONS: SampleConversation[] = []

function formatTimeAgo(isoDate?: string): string {
  if (!isoDate) return ""
  try {
    const diff = Math.floor((Date.now() - new Date(isoDate).getTime()) / 1000)
    if (diff < 60) return "just now"
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
    return new Date(isoDate).toLocaleDateString([], { month: "short", day: "numeric" })
  } catch {
    return ""
  }
}

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
  const [historyItems, setHistoryItems] = useState<SampleConversation[]>([])
  const [isDeletingId, setIsDeletingId] = useState<string | null>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  // Load history from both backend /api/history and local storage cache
  const loadHistory = async () => {
    let localList: SampleConversation[] = []
    try {
      const raw = localStorage.getItem("chai_chat_history")
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          localList = parsed
        }
      }
    } catch {}

    let remoteList: SampleConversation[] = []
    try {
      const headers: Record<string, string> = {}
      const sess = await supabase.auth.getSession()
      const tok = sess?.data?.session?.access_token || localStorage.getItem("chai_access_token")
      if (tok) headers["Authorization"] = `Bearer ${tok}`

      const res = await fetch(`${getApiBaseUrl()}/api/history`, { headers })
      if (res.ok) {
        const data = await res.json()
        if (Array.isArray(data)) {
          remoteList = data.map((d: any) => ({
            id: String(d.id),
            title: d.title || d.prompt || "Conversation",
            mode: (d.mode || "ask") as AssistantMode,
            layout: (d.layout || "chat") as WorkspaceLayout,
            prompt: d.prompt || d.messages?.[0]?.content || d.title,
            answer: d.answer || d.messages?.[1]?.content || "",
            messages: d.messages,
            createdAt: d.created_at,
          }))
        }
      }
    } catch {
      // offline or backend fallback
    }

    // Merge: remote records + local records (dedup by ID and prompt snippet)
    const combined: SampleConversation[] = []
    const seenIds = new Set<string>()
    const seenPrompts = new Set<string>()

    for (const item of [...remoteList, ...localList]) {
      const pSnippet = (item.prompt || "").slice(0, 50).trim()
      if (seenIds.has(item.id)) continue
      if (pSnippet && seenPrompts.has(pSnippet)) continue

      seenIds.add(item.id)
      if (pSnippet) seenPrompts.add(pSnippet)
      combined.push(item)
    }

    setHistoryItems(combined)

    // Sync back to local storage cache for offline resilience
    if (combined.length > 0) {
      try {
        localStorage.setItem("chai_chat_history", JSON.stringify(combined.slice(0, 50)))
      } catch {}
    }
  }

  useEffect(() => {
    if (open) {
      loadHistory()
    }
  }, [open])

  const handleDeleteItem = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    setIsDeletingId(id)

    // Update state and local storage immediately
    const updated = historyItems.filter((item) => item.id !== id)
    setHistoryItems(updated)
    try {
      localStorage.setItem("chai_chat_history", JSON.stringify(updated))
    } catch {}

    // Call backend delete
    try {
      const headers: Record<string, string> = {}
      const sess = await supabase.auth.getSession()
      const tok = sess?.data?.session?.access_token
      if (tok) headers["Authorization"] = `Bearer ${tok}`

      await fetch(`${getApiBaseUrl()}/api/history/${encodeURIComponent(id)}`, {
        method: "DELETE",
        headers,
      })
    } catch {}

    setIsDeletingId(null)
  }

  const handleClearAll = async () => {
    setHistoryItems([])
    try {
      localStorage.removeItem("chai_chat_history")
    } catch {}
    try {
      await fetch(`${getApiBaseUrl()}/api/history`, { method: "DELETE" })
    } catch {}
  }

  const recentItems = useMemo(() => {
    const current =
      currentTitle && currentTitle !== "New chat"
        ? [
            {
              id: "current",
              title: currentTitle,
              current: true as const,
              sample: null,
              isGitRepo: false,
              createdAt: undefined,
            },
          ]
        : []

    const userHistory = historyItems.map((item) => ({
      id: item.id,
      title: item.title,
      current: false as const,
      sample: item,
      isGitRepo: Boolean(item.isGitRepo),
      createdAt: item.createdAt,
    }))

    // If no real conversation history exists yet, show starter templates
    const fallbackStarters =
      userHistory.length === 0
        ? STARTER_CONVERSATIONS.map((sample) => ({
            id: sample.id,
            title: sample.title,
            current: false as const,
            sample,
            isGitRepo: true,
            createdAt: undefined,
          }))
        : []

    const all = [...current, ...userHistory, ...fallbackStarters]
    const query = searchTerm.trim().toLowerCase()
    if (!query) return all
    return all.filter((item) => item.title.toLowerCase().includes(query))
  }, [currentTitle, searchTerm, historyItems])

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
      className="absolute left-3 top-[56px] z-50 flex max-h-[min(80dvh,540px)] w-[min(380px,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-border/80 bg-popover/95 text-popover-foreground shadow-2xl backdrop-blur-xl animate-in fade-in-0 zoom-in-95 duration-150"
    >
      <div className="flex items-center justify-between border-b border-border/70 px-4 py-3 bg-muted/30">
        <div className="flex items-center gap-2">
          <Clock className="size-4 text-primary" />
          <h2 className="text-xs font-semibold tracking-tight">Conversation History</h2>
          <span className="rounded-full bg-primary/10 px-1.5 py-0.2 text-[10px] font-medium text-primary">
            {historyItems.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {historyItems.length > 0 && (
            <button
              type="button"
              onClick={handleClearAll}
              title="Clear all conversations"
              className="px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition"
            >
              Clear
            </button>
          )}
          <button
            type="button"
            aria-label="Close conversation history"
            onClick={onClose}
            className="grid size-7 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </div>
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

      <div className="flex-1 overflow-y-auto p-2 scrollbar-thin">
        <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center justify-between">
          <span>{historyItems.length > 0 ? "Recent Conversations" : "Recommended Starters"}</span>
          <span className="text-[9px] font-normal lowercase">{recentItems.length} items</span>
        </p>

        <div className="mt-1 flex flex-col gap-1">
          {recentItems.length === 0 ? (
            <div className="px-3 py-8 text-center text-xs text-muted-foreground">
              <MessageCircle className="size-6 mx-auto mb-2 opacity-30" />
              No conversations match your search.
            </div>
          ) : (
            recentItems.map((item) => {
              const isSelected = item.current
                ? activeHistoryId === "current"
                : activeHistoryId === item.id

              const timeStr = formatTimeAgo(item.createdAt)

              return (
                <div
                  key={item.id}
                  onClick={() => selectConversation(item)}
                  className={cn(
                    "group relative flex w-full cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-2 text-left text-xs transition",
                    isSelected
                      ? "bg-primary/15 text-primary font-medium"
                      : "hover:bg-muted/70 text-foreground",
                  )}
                >
                  <div className="flex items-center gap-2.5 min-w-0 flex-1">
                    {item.isGitRepo ? (
                      <Sparkles className="size-3.5 shrink-0 text-amber-500" />
                    ) : (
                      <MessageCircle className="size-3.5 shrink-0 text-muted-foreground group-hover:text-primary transition-colors" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate leading-snug">{item.title}</p>
                      {timeStr && (
                        <p className="text-[10px] text-muted-foreground/80 mt-0.5 leading-none">
                          {timeStr}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {item.isGitRepo && (
                      <span className="inline-flex shrink-0 items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
                        <FolderGit2 className="size-2.5" />
                        Starter
                      </span>
                    )}

                    {item.current && (
                      <span className="shrink-0 rounded bg-primary/20 px-1.5 py-0.5 text-[9px] text-primary font-medium">
                        Active
                      </span>
                    )}

                    {!item.current && !item.isGitRepo && (
                      <button
                        type="button"
                        title="Delete conversation"
                        disabled={isDeletingId === item.id}
                        onClick={(e) => handleDeleteItem(e, item.id)}
                        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/15 text-muted-foreground hover:text-destructive transition"
                      >
                        <Trash2 className="size-3" />
                      </button>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
