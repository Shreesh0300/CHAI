"use client"

import { LoaderCircle, MessageCircle } from "lucide-react"
import { ThinkingOrb } from "thinking-orbs"
import type { AssistantMode, ChatMessage, PromptInputMeta, DomainCategory, ExecutionTrackerState } from "@/components/chat-types"
import { ChatMessageRow } from "@/components/chat-message"
import { AgentExecutionTracker } from "@/components/agent-execution-tracker"
import { AiChatInput } from "@/components/ui/ai-chat-input"
import { Badge } from "@/components/ui/badge"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import { cn } from "@/lib/utils"

import { GenerationControls } from "@/components/generation-controls"

const MODE_LABELS: Record<AssistantMode, string> = {
  ask: "Ask",
  research: "Research",
  agent: "Agent",
}

interface ChatPanelProps {
  messages: ChatMessage[]
  mode: AssistantMode
  isResponding: boolean
  className?: string
  onSubmit: (value: string, meta: PromptInputMeta) => void
  onMicClick?: () => void
  category?: DomainCategory
  onCategoryChange?: (category: DomainCategory) => void
  liveTrackerState?: ExecutionTrackerState | null
  isChatModeResponding?: boolean
  isPaused?: boolean
  onPause?: () => void
  onResume?: () => void
  onCancel?: () => void
  selectedAgent?: string | null
  onSelectAgent?: (agentKey: string | null) => void
}

export function ChatPanel({
  messages,
  mode,
  isResponding,
  className,
  onSubmit,
  onMicClick,
  category,
  onCategoryChange,
  liveTrackerState,
  isChatModeResponding = false,
  isPaused = false,
  onPause,
  onResume,
  onCancel,
  selectedAgent,
  onSelectAgent,
}: ChatPanelProps) {
  return (
    <aside
      aria-label="Chat conversation panel"
      className={cn("min-h-0 min-w-0 flex-col overflow-hidden bg-background", className)}
    >
      <header className="flex min-h-[58px] shrink-0 items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <MessageCircle aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
          <h2 className="truncate text-sm font-semibold">Chat</h2>
          <Badge variant="secondary" className="shrink-0">
            {MODE_LABELS[mode]}
          </Badge>
        </div>
      </header>

      <MessageScrollerProvider>
        <MessageScroller className="min-h-0 flex-1">
          <MessageScrollerViewport
            role="log"
            aria-label="Conversation messages"
            aria-live="polite"
            aria-relevant="additions text"
            className="flex-1 px-3 sm:px-4"
          >
            <MessageScrollerContent className="mx-auto flex w-full max-w-[560px] flex-col gap-4 px-1 py-4">
              {messages.map((message, index) => (
                <MessageScrollerItem
                  key={message.id}
                  scrollAnchor={index === messages.length - 1 && !isResponding}
                >
                  <ChatMessageRow
                    message={message}
                    selectedAgent={selectedAgent}
                    onSelectAgent={onSelectAgent}
                  />
                </MessageScrollerItem>
              ))}
              {isResponding && (
                <MessageScrollerItem scrollAnchor>
                  <ThinkingRow
                    mode={mode}
                    liveTrackerState={liveTrackerState}
                    isChatModeResponding={isChatModeResponding}
                    isPaused={isPaused}
                    onPause={onPause}
                    onResume={onResume}
                    onCancel={onCancel}
                    selectedAgent={selectedAgent}
                    onSelectAgent={onSelectAgent}
                  />
                </MessageScrollerItem>
              )}
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
      </MessageScrollerProvider>

      <footer className="shrink-0 border-t border-border/70 bg-background/95 px-3 pb-3 pt-2 sm:px-4 sm:pb-4">
        <div className="mx-auto mb-2 flex w-full max-w-[560px] items-center gap-1.5 px-1 text-[11px] font-medium text-muted-foreground">
          <MessageCircle aria-hidden="true" className="size-3.5" />
          Continue the conversation
        </div>
        <div className="mx-auto w-full max-w-[560px]">
          <AiChatInput
            compact
            disabled={isResponding}
            placeholder="Ask a follow-up..."
            onSubmit={onSubmit}
            onMicClick={onMicClick}
            category={category}
            onCategoryChange={onCategoryChange}
          />
        </div>
        <p className="mx-auto mt-1.5 max-w-[560px] px-1 text-[10px] leading-4 text-muted-foreground">
          Enter sends · Shift+Enter creates a new line
        </p>
      </footer>
    </aside>
  )
}

function ThinkingRow({
  mode,
  liveTrackerState,
  isChatModeResponding,
  isPaused,
  onPause,
  onResume,
  onCancel,
  selectedAgent,
  onSelectAgent,
}: {
  mode: AssistantMode
  liveTrackerState?: ExecutionTrackerState | null
  isChatModeResponding?: boolean
  isPaused?: boolean
  onPause?: () => void
  onResume?: () => void
  onCancel?: () => void
  selectedAgent?: string | null
  onSelectAgent?: (agentKey: string | null) => void
}) {
  const hasControls = Boolean(onPause && onResume && onCancel)

  if (isChatModeResponding) {
    return (
      <Marker
        role="status"
        aria-live="polite"
        className="rounded-lg border border-border/70 bg-muted/40 px-3 py-2 text-xs"
      >
        <MarkerIcon>
          {isPaused ? (
            <span className="size-2 rounded-full bg-amber-400" />
          ) : (
            <LoaderCircle aria-hidden="true" className="size-3.5 animate-spin text-primary" />
          )}
        </MarkerIcon>
        <MarkerContent>
          <span className="font-medium text-foreground">
            {isPaused ? "Paused" : "CHAI is responding..."}
          </span>
        </MarkerContent>
        {hasControls ? (
          <GenerationControls
            isPaused={Boolean(isPaused)}
            onPause={onPause!}
            onResume={onResume!}
            onCancel={onCancel!}
            compact
            className="ml-auto"
          />
        ) : (
          !isPaused && (
            <span aria-hidden="true" className="ml-auto flex items-center gap-1">
              <span className="size-1.5 animate-pulse rounded-full bg-primary/70" />
              <span className="size-1.5 animate-pulse rounded-full bg-primary/70 [animation-delay:120ms]" />
              <span className="size-1.5 animate-pulse rounded-full bg-primary/70 [animation-delay:240ms]" />
            </span>
          )
        )}
      </Marker>
    )
  }

  if (liveTrackerState && liveTrackerState.mode === "solve") {
    return (
      <div className="w-full">
        <AgentExecutionTracker
          state={liveTrackerState}
          isLive={true}
          defaultExpanded={false}
          isPaused={isPaused}
          onPause={onPause}
          onResume={onResume}
          onCancel={onCancel}
          selectedAgent={selectedAgent}
          onSelectAgent={onSelectAgent}
        />
      </div>
    )
  }

  const isAgentMode = mode === "agent"

  return (
    <Marker
      role="status"
      aria-live="polite"
      className="rounded-lg border border-border/70 bg-muted/40 px-3 py-2 text-xs"
    >
      <MarkerIcon className={isAgentMode ? "size-5" : undefined}>
        {isPaused ? (
          <span className="size-2 rounded-full bg-amber-400" />
        ) : isAgentMode ? (
          <ThinkingOrb
            state="working"
            size={20}
            theme="auto"
            aria-label="Agent is working"
          />
        ) : (
          <LoaderCircle aria-hidden="true" className="size-3.5 animate-spin text-primary" />
        )}
      </MarkerIcon>
      <MarkerContent>
        {isPaused
          ? "Paused"
          : isAgentMode
          ? "CHAI is coordinating your workflow..."
          : "CHAI is analyzing your request..."}
      </MarkerContent>
      {hasControls ? (
        <GenerationControls
          isPaused={Boolean(isPaused)}
          onPause={onPause!}
          onResume={onResume!}
          onCancel={onCancel!}
          compact
          className="ml-auto"
        />
      ) : (
        !isPaused && !isAgentMode && (
          <span aria-hidden="true" className="ml-auto flex items-center gap-1">
            <span className="size-1.5 animate-pulse rounded-full bg-primary/70" />
            <span className="size-1.5 animate-pulse rounded-full bg-primary/70 [animation-delay:120ms]" />
            <span className="size-1.5 animate-pulse rounded-full bg-primary/70 [animation-delay:240ms]" />
          </span>
        )
      )}
    </Marker>
  )
}
