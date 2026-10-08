"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { History, LoaderCircle, MessageCircle, PanelRight, Plus, Sparkles } from "lucide-react"
import { AssistantSpeech } from "@/components/assistant-speech"
import { ScreenEdgeIllumination } from "@/components/screen-edge-illumination"
import {
  createAssistantReply,
  createConversationTitle,
  createId,
  createWorkArtifact,
  EMPTY_PROMPT_META,
  formatAttachmentPrompt,
  MODE_DETAILS,
  QUICK_PROMPTS,
  shouldOpenWorkPane,
} from "@/components/chat-types"
import type {
  AssistantMode,
  ChatMessage,
  PromptInputMeta,
  PromptSuggestion,
  WorkspaceLayout,
} from "@/components/chat-types"
import { ChatHistoryPopover, type SampleConversation } from "@/components/chat-sidebar"
import { ChatHero } from "@/components/chat-hero"
import { ChatPanel } from "@/components/chat-panel"
import { ProfileMenu, type ProfileMenuUser } from "@/components/profile-menu"
import { ThinkingOrb } from "thinking-orbs"
import { AiChatInput } from "@/components/ui/ai-chat-input"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { WorkResults } from "@/components/workspace-panel"
import { playAssistantAudio, stopAssistantAudio } from "@/lib/assistant-audio"
import { cn } from "@/lib/utils"

type MobilePane = "response" | "chat"
type SubmitOptions = {
  mode?: AssistantMode
  forceWorkspace?: boolean
  fromChatPanel?: boolean
}

const MODE_LABELS: Record<AssistantMode, string> = {
  ask: "Quick answer",
  research: "Research",
  agent: "Agent",
}

export function ChatWorkspace({ user }: { user: ProfileMenuUser | null }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [mode, setMode] = useState<AssistantMode>("ask")
  const [layout, setLayout] = useState<WorkspaceLayout>("chat")
  const [work, setWork] = useState<ReturnType<typeof createWorkArtifact> | null>(null)
  const [conversationTitle, setConversationTitle] = useState("New chat")
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null)
  const [isResponding, setIsResponding] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [mobilePane, setMobilePane] = useState<MobilePane>("response")
  const [isSpeechAssistantOpen, setIsSpeechAssistantOpen] = useState(false)
  const [isWakeWordIlluminated, setIsWakeWordIlluminated] = useState(false)
  const historyTriggerRef = useRef<HTMLButtonElement | null>(null)
  const responseTimer = useRef<number | null>(null)
  const closeHistory = useCallback(() => setHistoryOpen(false), [])

  // Wake word ("Hey CHAI") continuous background detection
  useEffect(() => {
    if (typeof window === "undefined") return

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) return

    let recognition: any = null
    let active = true

    function startWakeWordListener() {
      if (!active || isSpeechAssistantOpen) return

      try {
        recognition = new SpeechRecognition()
        recognition.continuous = true
        recognition.interimResults = true
        recognition.lang = "en-US"

        recognition.onresult = (event: any) => {
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript.toLowerCase()
            if (
              transcript.includes("hey chai") ||
              transcript.includes("hey chye") ||
              transcript.includes("hay chai") ||
              transcript.includes("hi chai") ||
              transcript.includes("ok chai")
            ) {
              console.log("Wake word 'Hey CHAI' detected:", transcript)
              setIsWakeWordIlluminated(true)
              setIsSpeechAssistantOpen(true)
              setTimeout(() => setIsWakeWordIlluminated(false), 3000)
              try {
                recognition.stop()
              } catch {}
              break
            }
          }
        }

        recognition.onerror = () => {
          // Ignore normal recognition errors
        }

        recognition.onend = () => {
          if (active && !isSpeechAssistantOpen) {
            setTimeout(() => {
              if (active && !isSpeechAssistantOpen) {
                startWakeWordListener()
              }
            }, 600)
          }
        }

        recognition.start()
      } catch {
        // Recognition will resume when user allows or interacts
      }
    }

    startWakeWordListener()

    return () => {
      active = false
      if (recognition) {
        try {
          recognition.abort()
        } catch {}
      }
    }
  }, [isSpeechAssistantOpen])

  useEffect(() => {
    return () => {
      if (responseTimer.current !== null) window.clearTimeout(responseTimer.current)
    }
  }, [])

  function cancelPendingResponse() {
    if (responseTimer.current !== null) {
      window.clearTimeout(responseTimer.current)
      responseTimer.current = null
    }
    setIsResponding(false)
  }

  function startNewChat() {
    cancelPendingResponse()
    setMessages([])
    setMode("ask")
    setLayout("chat")
    setWork(null)
    setConversationTitle("New chat")
    setActiveHistoryId(null)
    setHistoryOpen(false)
    setMobilePane("response")
  }

  function returnToCurrentConversation() {
    setMobilePane("response")
    setHistoryOpen(false)
  }

  function openSampleConversation(sample: SampleConversation) {
    cancelPendingResponse()
    const userMessage: ChatMessage = {
      id: createId(),
      role: "user",
      content: sample.prompt,
    }
    const assistantMessage: ChatMessage = {
      id: createId(),
      role: "assistant",
      content:
        sample.answer ?? createAssistantReply(sample.prompt, sample.layout, false),
    }

    setMessages([userMessage, assistantMessage])
    setMode(sample.mode)
    setLayout(sample.layout)
    setWork(sample.layout === "workspace" ? createWorkArtifact(sample.prompt) : null)
    setConversationTitle(sample.title)
    setActiveHistoryId(sample.id)
    setHistoryOpen(false)
    setMobilePane("response")
  }

  async function submitPrompt(
    rawPrompt: string,
    meta: PromptInputMeta,
    options: SubmitOptions = {},
  ): Promise<string> {
    const prompt = rawPrompt.trim() || formatAttachmentPrompt(meta.attachments)
    if (!prompt || isResponding) return ""

    const selectedMode = options.mode ?? mode
    const fromChatPanel = options.fromChatPanel ?? false
    const nextLayout: WorkspaceLayout =
      options.forceWorkspace || shouldOpenWorkPane(prompt, selectedMode, meta.attachments.length)
        ? "workspace"
        : "chat"
    const isFollowUp = messages.length > 0
    const userMessage: ChatMessage = {
      id: createId(),
      role: "user",
      content: prompt,
      attachments: meta.attachments.map((file) => file.name),
    }

    if (messages.length === 0) setConversationTitle(createConversationTitle(prompt))
    setActiveHistoryId("current")
    setMode(selectedMode)
    setLayout(nextLayout)
    setHistoryOpen(false)
    setMobilePane(fromChatPanel ? "chat" : "response")
    setMessages((current) => [...current, userMessage])

    if (nextLayout === "workspace") {
      if (layout !== "workspace" || !work) {
        setWork(createWorkArtifact(prompt))
      }
    } else {
      setWork(null)
    }

    setIsResponding(true)

    try {
      const payload: Record<string, any> = { message: prompt, problem: prompt }
      if (selectedMode && selectedMode !== "ask") {
        payload.mode = selectedMode
      }
      if (user?.id) {
        payload.user_id = user.id
      }
      let res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        res = await fetch(`${API_BASE}/api/solve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
      }
      if (!res.ok) throw new Error("API error")
      const data = await res.json()
      const rawContent =
        data.final_answer ||
        data.final_synthesized_answer ||
        createAssistantReply(prompt, nextLayout, isFollowUp)
      const content = rawContent.replace(/\\u([0-9a-fA-F]{4})/g, (_: string, hex: string) =>
        String.fromCharCode(parseInt(hex, 16))
      )
      const assistantMessage: ChatMessage = {
        id: createId(),
        role: "assistant",
        content,
      }
      setMessages((current) => [...current, assistantMessage])
      setIsResponding(false)
      if (meta.isVoice && !isSpeechAssistantOpen) {
        playAssistantAudio(content, meta.language || data.language || "en")
      }
      return content
    } catch {
      const content = createAssistantReply(prompt, nextLayout, isFollowUp)
      const assistantMessage: ChatMessage = {
        id: createId(),
        role: "assistant",
        content,
      }
      setMessages((current) => [...current, assistantMessage])
      setIsResponding(false)
      return content
    }
  }

  function chooseSuggestion(suggestion: PromptSuggestion) {
    submitPrompt(suggestion.prompt, EMPTY_PROMPT_META, { mode: suggestion.mode })
  }

  return (
    <div className="flex h-dvh min-h-[560px] w-full overflow-hidden bg-background text-foreground">
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[58px] shrink-0 items-center justify-between gap-3 border-b border-border/70 px-3.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground">
              <Sparkles aria-hidden="true" className="size-4" />
            </span>
            <div className="hidden min-w-[76px] shrink-0 sm:block">
              <p className="text-sm font-semibold tracking-tight">CHAI</p>
              <p className="text-[11px] text-muted-foreground">AI workspace</p>
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={startNewChat}
              className="gap-1.5"
            >
              <Plus data-icon="inline-start" />
              <span className="hidden sm:inline">New chat</span>
              <span className="sm:hidden">New</span>
            </Button>

            <div className="relative shrink-0">
              <button
                ref={historyTriggerRef}
                type="button"
                aria-label="Recent conversations"
                aria-haspopup="dialog"
                aria-expanded={historyOpen}
                aria-controls="recent-conversations-popover"
                onClick={() => setHistoryOpen((current) => !current)}
                className={cn(
                  "inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border border-transparent px-2.5 text-xs font-medium text-muted-foreground transition hover:bg-muted/70 hover:text-foreground",
                  historyOpen && "bg-muted text-foreground",
                )}
              >
                <History aria-hidden="true" className="size-4" />
                <span className="hidden sm:inline">Recent</span>
              </button>
              <ChatHistoryPopover
                open={historyOpen}
                currentTitle={conversationTitle}
                activeHistoryId={activeHistoryId}
                triggerRef={historyTriggerRef}
                onOpenSample={openSampleConversation}
                onReturnToCurrent={returnToCurrentConversation}
                onClose={closeHistory}
              />
            </div>
          </div>

          <div className="hidden min-w-0 flex-1 px-4 text-center md:block">
            <p className="truncate text-sm font-medium">{conversationTitle}</p>
            <p className="truncate text-[11px] text-muted-foreground">
              {layout === "workspace"
                ? "A spacious response canvas with chat alongside"
                : "A clear answer, without the clutter"}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {layout === "workspace" && (
              <Badge variant="secondary" className="hidden shrink-0 gap-1 sm:inline-flex">
                <PanelRight data-icon="inline-start" />
                Work view
              </Badge>
            )}
            <ProfileMenu user={user} />
          </div>
        </header>

        {messages.length > 0 && (
          <div
            role="group"
            aria-label="Choose response or chat"
            className="grid shrink-0 grid-cols-2 gap-1 border-b border-border/70 bg-muted/30 p-2 lg:hidden"
          >
            <button
              type="button"
              aria-pressed={mobilePane === "response"}
              onClick={() => setMobilePane("response")}
              className={cn(
                "flex min-h-9 items-center justify-center gap-2 rounded-lg px-3 text-xs font-medium text-muted-foreground transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                mobilePane === "response" && "bg-card text-foreground shadow-sm",
              )}
            >
              <PanelRight aria-hidden="true" className="size-3.5" />
              Response
            </button>
            <button
              type="button"
              aria-pressed={mobilePane === "chat"}
              onClick={() => setMobilePane("chat")}
              className={cn(
                "flex min-h-9 items-center justify-center gap-2 rounded-lg px-3 text-xs font-medium text-muted-foreground transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                mobilePane === "chat" && "bg-card text-foreground shadow-sm",
              )}
            >
              <MessageCircle aria-hidden="true" className="size-3.5" />
              Chat
            </button>
          </div>
        )}

        <div className="flex min-h-0 flex-1 overflow-hidden">
          <section
            id="response-canvas"
            aria-label="Response canvas"
            className={cn(
              "min-h-0 min-w-0 flex-1",
              layout === "workspace" && work ? "flex flex-col overflow-hidden" : "overflow-y-auto",
              messages.length > 0 && mobilePane === "chat"
                ? layout === "workspace" && work
                  ? "hidden lg:flex"
                  : "hidden lg:block"
                : layout === "workspace" && work
                  ? "flex"
                  : "block",
            )}
          >
            {messages.length === 0 ? (
              <div className="mx-auto flex min-h-full w-full max-w-[1180px] flex-col items-center justify-center px-4 py-6 sm:px-7 sm:py-8">
                <ChatHero
                  suggestions={QUICK_PROMPTS}
                  onChoose={chooseSuggestion}
                  composer={
                    <>
                      <ResponseModePicker mode={mode} onChange={setMode} />
                      <AiChatInput
                        disabled={isResponding}
                        onSubmit={(value, meta) => submitPrompt(value, meta)}
                        onMicClick={() => setIsSpeechAssistantOpen(true)}
                      />
                      <p className="mt-2 text-center text-[10px] leading-4 text-muted-foreground">
                        Enter to send · Shift+Enter for a new line · Tap mic or say &quot;Hey CHAI&quot;
                      </p>
                    </>
                  }
                />
              </div>
            ) : layout === "workspace" && work ? (
              <div className="flex min-h-0 flex-1 flex-col">
                <div className="min-h-0 flex-1 overflow-y-auto">
                  <div className="mx-auto w-full max-w-[1480px] px-4 py-5 sm:px-6 sm:py-7 xl:px-8">
                    <WorkResults artifact={work} />
                  </div>
                </div>
              </div>
            ) : (
              <AnswerCanvas
                title={conversationTitle}
                messages={messages}
                mode={mode}
                isResponding={isResponding}
              />
            )}
          </section>

          {messages.length > 0 && (
            <ChatPanel
              messages={messages}
              mode={mode}
              isResponding={isResponding}
              onSubmit={(value, meta) =>
                submitPrompt(value, meta, {
                  forceWorkspace: layout === "workspace",
                  fromChatPanel: true,
                })
              }
              onMicClick={() => setIsSpeechAssistantOpen(true)}
              className={cn(
                "min-h-0 w-full flex-col border-t border-border/70 bg-background lg:w-[390px] lg:flex-none lg:border-l lg:border-t-0 xl:w-[420px]",
                mobilePane === "chat" ? "flex" : "hidden lg:flex",
              )}
            />
          )}
        </div>

        {/* Screen corners and edge illumination when Hey CHAI is detected */}
        <ScreenEdgeIllumination active={isWakeWordIlluminated} />

        {/* Futuristic AI Voice Assistant Centerpiece Modal */}
        {isSpeechAssistantOpen && (
          <div className="fixed inset-0 z-50 animate-in fade-in zoom-in-95 duration-300">
            <AssistantSpeech
              onBack={() => {
                stopAssistantAudio()
                setIsSpeechAssistantOpen(false)
              }}
              onSubmitVoicePrompt={async (voicePrompt) => {
                return await submitPrompt(
                  voicePrompt,
                  { attachments: [], isVoice: true },
                  { fromChatPanel: true },
                )
              }}
            />
          </div>
        )}
      </main>
    </div>
  )
}

function ResponseModePicker({
  mode,
  onChange,
}: {
  mode: AssistantMode
  onChange: (mode: AssistantMode) => void
}) {
  return (
    <div className="mb-2 flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Response mode
        </span>
        <span className="hidden text-[10px] text-muted-foreground sm:inline">
          {MODE_DETAILS[mode].description}
        </span>
      </div>
      <ToggleGroup
        aria-label="Response mode"
        value={[mode]}
        onValueChange={(values) => {
          if (values[0]) onChange(values[0] as AssistantMode)
        }}
        variant="outline"
        size="sm"
        className="w-fit"
      >
        <ToggleGroupItem value="ask">Ask</ToggleGroupItem>
        <ToggleGroupItem value="research">Research</ToggleGroupItem>
        <ToggleGroupItem value="agent">Agent</ToggleGroupItem>
      </ToggleGroup>
    </div>
  )
}

function AnswerCanvas({
  title,
  messages,
  mode,
  isResponding,
}: {
  title: string
  messages: ChatMessage[]
  mode: AssistantMode
  isResponding: boolean
}) {
  const latestUserMessage = [...messages].reverse().find((message) => message.role === "user")
  const latestAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant")

  return (
    <article className="mx-auto w-full max-w-[1160px] px-5 py-8 sm:px-8 sm:py-10 xl:px-12">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{MODE_LABELS[mode]}</Badge>
        <span className="text-xs text-muted-foreground">Response canvas</span>
      </div>
      <h1 className="mt-5 max-w-4xl text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
        {title}
      </h1>

      {latestUserMessage && (
        <section className="mt-7 max-w-[88ch] rounded-2xl border border-border/80 bg-muted/40 p-4 sm:p-5">
          <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Your prompt
          </p>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-foreground">
            {latestUserMessage.content}
          </p>
        </section>
      )}

      <section aria-label="Assistant response" className="mt-8 max-w-[88ch]">
        {isResponding || !latestAssistantMessage ? (
          <Marker
            role="status"
            aria-live="polite"
            className="rounded-2xl border border-border/80 bg-card px-5 py-4 text-sm"
          >
            <MarkerIcon className={mode === "agent" ? "size-5" : undefined}>
              {mode === "agent" ? (
                <ThinkingOrb
                  state="working"
                  size={20}
                  theme="auto"
                  aria-label="Agent is working"
                />
              ) : (
                <LoaderCircle aria-hidden="true" className="animate-spin text-primary" />
              )}
            </MarkerIcon>
            <MarkerContent>
              {mode === "agent"
                ? "CHAI is coordinating your workflow..."
                : "Thinking through your prompt..."}
            </MarkerContent>
          </Marker>
        ) : (
          <div className="whitespace-pre-wrap break-words text-[1rem] leading-8 text-foreground sm:text-[1.05rem]">
            {latestAssistantMessage.content}
          </div>
        )}
      </section>

      <div className="mt-12 flex max-w-[88ch] items-center gap-3 border-t border-border/70 pt-4 text-sm text-muted-foreground">
        <MessageCircle aria-hidden="true" className="size-4 shrink-0" />
        <p>Keep exploring in the chat panel on the right.</p>
      </div>
    </article>
  )
}
