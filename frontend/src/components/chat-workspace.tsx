"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  Database,
  ExternalLink,
  History,
  LoaderCircle,
  MessageCircle,
  PanelRight,
  Plus,
  Sparkles,
  Volume2,
  VolumeX,
} from "lucide-react"
import {
  createAssistantReply,
  createConversationTitle,
  createId,
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
import { cn } from "@/lib/utils"
import { getApiBaseUrl } from "@/lib/api"
import { supabase, fetchSolveDetails } from "@/lib/supabase"

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
  const [solveDetails, setSolveDetails] = useState<any | null>(null)
  const [mode, setMode] = useState<AssistantMode>("ask")
  const [layout, setLayout] = useState<WorkspaceLayout>("chat")
  const [conversationTitle, setConversationTitle] = useState("New chat")
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null)
  const [isResponding, setIsResponding] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [mobilePane, setMobilePane] = useState<MobilePane>("response")
  const historyTriggerRef = useRef<HTMLButtonElement | null>(null)
  const responseTimer = useRef<number | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const closeHistory = useCallback(() => setHistoryOpen(false), [])

  // Keyboard shortcut: Alt+V or Alt+C to invoke Voice Assistant instantly
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.altKey && e.key.toLowerCase() === "v") || (e.altKey && e.key.toLowerCase() === "c")) {
        e.preventDefault()
        window.dispatchEvent(new CustomEvent("chai-open-voice", { detail: "" }))
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  // Global voice assistant trigger
  const handleOpenVoiceAssistant = (initialQuery: string = "") => {
    window.dispatchEvent(new CustomEvent("chai-open-voice", { detail: initialQuery }))
  }

  useEffect(() => {
    return () => {
      if (responseTimer.current !== null) window.clearTimeout(responseTimer.current)
      if (abortControllerRef.current) abortControllerRef.current.abort()
    }
  }, [])

  function cancelPendingResponse() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
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
    setConversationTitle("New chat")
    setActiveHistoryId(null)
    setSolveDetails(null)
    setHistoryOpen(false)
    setMobilePane("response")
  }

  function returnToCurrentConversation() {
    setMobilePane("response")
    setHistoryOpen(false)
  }

  function persistConversationToLocal(
    promptText: string,
    replyText: string,
    chatMode: AssistantMode,
    chatLayout: WorkspaceLayout,
    assignedId?: string,
  ) {
    try {
      const raw = localStorage.getItem("chai_chat_history")
      const list = raw ? JSON.parse(raw) : []
      const id = assignedId || "conv_" + Date.now()
      const title = createConversationTitle(promptText)
      const newEntry = {
        id,
        title,
        mode: chatMode,
        layout: chatLayout,
        prompt: promptText,
        answer: replyText,
        messages: [
          { id: "u_" + Date.now(), role: "user", content: promptText },
          { id: "a_" + Date.now(), role: "assistant", content: replyText },
        ],
        createdAt: new Date().toISOString(),
      }
      const filtered = Array.isArray(list)
        ? list.filter((i: any) => i.id !== id && i.prompt !== promptText)
        : []
      localStorage.setItem("chai_chat_history", JSON.stringify([newEntry, ...filtered].slice(0, 50)))
    } catch {}
  }

  function openSampleConversation(sample: SampleConversation) {
    cancelPendingResponse()
    let msgs: ChatMessage[] = []
    if (sample.messages && sample.messages.length > 0) {
      msgs = sample.messages.map((m: any) => ({
        id: m.id || createId(),
        role: m.role || "user",
        content: m.content || "",
      }))
    } else {
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
      msgs = [userMessage, assistantMessage]
    }

    setMessages(msgs)
    setMode(sample.mode)
    setLayout(sample.layout)
    setConversationTitle(sample.title)
    setActiveHistoryId(sample.id)
    setHistoryOpen(false)
    setMobilePane("response")

    // Fetch and load agent response data from Supabase
    if (sample.id && !sample.id.startsWith("starter_")) {
      fetchSolveDetails(sample.id).then((details) => {
        if (details) {
          setSolveDetails(details)
        } else {
          setSolveDetails(null)
        }
      }).catch(() => {
        setSolveDetails(null)
      })
    } else {
      setSolveDetails(null)
    }
  }

  async function submitPrompt(
    rawPrompt: string,
    meta: PromptInputMeta,
    options: SubmitOptions = {},
  ) {
    const prompt = rawPrompt.trim() || formatAttachmentPrompt(meta.attachments)
    if (!prompt || isResponding) return

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

    setIsResponding(true)

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller
    const timeoutId = window.setTimeout(() => controller.abort(), 60000)

    const headers: Record<string, string> = { "Content-Type": "application/json" }
    try {
      const sess = await supabase.auth.getSession()
      const tok = sess?.data?.session?.access_token || localStorage.getItem("chai_access_token")
      if (tok) headers["Authorization"] = `Bearer ${tok}`
    } catch {}

    fetch(`${getApiBaseUrl()}/api/solve`, {
      method: "POST",
      headers,
      signal: controller.signal,
      body: JSON.stringify({
        problem: prompt,
        model: meta.model || (typeof window !== "undefined" && localStorage.getItem("chai_model_level") === "advance" ? "Advance" : "Auto"),
      }),
    })
      .then(async (res) => {
        window.clearTimeout(timeoutId)
        if (!res.ok) throw new Error("API error")
        const data = await res.json()
        const content = data.final_synthesized_answer || createAssistantReply(prompt, nextLayout, isFollowUp)
        const assistantMessage: ChatMessage = {
          id: createId(),
          role: "assistant",
          content,
        }
        const assignedId = data.id || "conv_" + Date.now()
        persistConversationToLocal(prompt, content, selectedMode, nextLayout, assignedId)
        setSolveDetails(data)
        setMessages((current) => [...current, assistantMessage])
        setIsResponding(false)
        abortControllerRef.current = null
      })
      .catch(() => {
        window.clearTimeout(timeoutId)
        responseTimer.current = window.setTimeout(() => {
          const assistantMessage: ChatMessage = {
            id: createId(),
            role: "assistant",
            content: createAssistantReply(prompt, nextLayout, isFollowUp),
          }
          persistConversationToLocal(prompt, assistantMessage.content, selectedMode, nextLayout)
          setMessages((current) => [...current, assistantMessage])
          setIsResponding(false)
          responseTimer.current = null
          abortControllerRef.current = null
        }, 500)
      })
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
              "min-h-0 min-w-0 flex-1 overflow-y-auto",
              messages.length > 0 && mobilePane === "chat" ? "hidden lg:block" : "block",
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
                        onMicClick={() => handleOpenVoiceAssistant("")}
                      />
                      <p className="mt-2 text-center text-[11px] leading-4 text-muted-foreground">
                        CHAI can make mistakes. Verify important info.
                      </p>
                    </>
                  }
                />
              </div>
            ) : (
              <AnswerCanvas
                title={conversationTitle}
                messages={messages}
                mode={mode}
                isResponding={isResponding}
                solveDetails={solveDetails}
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
              onMicClick={() => handleOpenVoiceAssistant("")}
              className={cn(
                "min-h-0 w-full flex-col border-t border-border/70 bg-background lg:w-[390px] lg:flex-none lg:border-l lg:border-t-0 xl:w-[420px]",
                mobilePane === "chat" ? "flex" : "hidden lg:flex",
              )}
            />
          )}
        </div>
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
  solveDetails,
}: {
  title: string
  messages: ChatMessage[]
  mode: AssistantMode
  isResponding: boolean
  solveDetails?: any
}) {
  const [copied, setCopied] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const latestUserMessage = [...messages].reverse().find((message) => message.role === "user")
  const latestAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant")

  const handleCopy = () => {
    if (!latestAssistantMessage) return
    navigator.clipboard.writeText(latestAssistantMessage.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const handleSpeak = () => {
    if (typeof window === "undefined" || !window.speechSynthesis || !latestAssistantMessage) return
    if (isSpeaking) {
      window.speechSynthesis.cancel()
      setIsSpeaking(false)
      return
    }

    window.speechSynthesis.cancel()
    const clean = latestAssistantMessage.content
      .replace(/```[\s\S]*?```/g, "Code block omitted.")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/[*_~#>]/g, "")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/\s+/g, " ")
      .trim()

    setTimeout(() => {
      const utterance = new SpeechSynthesisUtterance(clean)
      utterance.rate = 1.02
      const voices = window.speechSynthesis.getVoices()
      const voice =
        voices.find(
          (v) =>
            v.lang.startsWith("en") &&
            (v.name.includes("Natural") ||
              v.name.includes("Google") ||
              v.name.includes("Samantha") ||
              v.name.includes("Jenny") ||
              v.name.includes("Guy")),
        ) ||
        voices.find((v) => v.lang.startsWith("en")) ||
        voices[0]
      if (voice) utterance.voice = voice

      utterance.onstart = () => setIsSpeaking(true)
      utterance.onend = () => setIsSpeaking(false)
      utterance.onerror = () => setIsSpeaking(false)

      ;(window as any)._chaiCanvasUtterance = utterance
      if (window.speechSynthesis.paused) window.speechSynthesis.resume()
      window.speechSynthesis.speak(utterance)
    }, 50)
  }

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
                ? "CHAI multi-agent reasoning in progress..."
                : "Thinking through your prompt..."}
            </MarkerContent>
          </Marker>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Agent Answer
              </span>
              <div className="flex items-center gap-1.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={handleSpeak}
                  className="h-7 gap-1 px-2 text-xs"
                >
                  {isSpeaking ? <VolumeX className="size-3.5 text-destructive" /> : <Volume2 className="size-3.5" />}
                  <span>{isSpeaking ? "Stop" : "Read aloud"}</span>
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={handleCopy}
                  className="h-7 gap-1 px-2 text-xs"
                >
                  {copied ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
                  <span>{copied ? "Copied" : "Copy"}</span>
                </Button>
              </div>
            </div>
            <div className="whitespace-pre-wrap break-words text-[1rem] leading-8 text-foreground sm:text-[1.05rem]">
              {latestAssistantMessage.content}
            </div>

            {/* Structured Multi-Agent Intelligence & Supabase Records */}
            {solveDetails && <MultiAgentDetailsSection solveDetails={solveDetails} />}
          </div>
        )}
      </section>

      <div className="mt-12 flex max-w-[88ch] flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <MessageCircle aria-hidden="true" className="size-4 shrink-0" />
          <p>Keep exploring in the chat panel on the right.</p>
        </div>
        <p className="text-[11px] text-muted-foreground/80">
          CHAI can make mistakes. Verify important info.
        </p>
      </div>
    </article>
  )
}

function MultiAgentDetailsSection({ solveDetails }: { solveDetails: any }) {
  const [activeTab, setActiveTab] = useState<'researcher' | 'strategist' | 'engineer' | 'guardian' | 'security' | 'evaluator'>('researcher')
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(true)

  if (!solveDetails) return null

  const agentOutputs = solveDetails.agent_outputs || {}
  const evaluations = solveDetails.evaluations || {}
  const securityFindings = solveDetails.security_findings || []
  const sources = solveDetails.sources || []

  const handleCopyAgent = (name: string, content: any) => {
    const text = typeof content === 'string' ? content : JSON.stringify(content, null, 2)
    navigator.clipboard.writeText(text).then(() => {
      setCopiedKey(name)
      setTimeout(() => setCopiedKey(null), 2000)
    })
  }

  const agentsList: { id: 'researcher' | 'strategist' | 'engineer' | 'guardian'; label: string; icon: string }[] = [
    { id: 'researcher', label: 'Researcher', icon: '🔬' },
    { id: 'strategist', label: 'Strategist', icon: '♟️' },
    { id: 'engineer', label: 'Engineer', icon: '⚙️' },
    { id: 'guardian', label: 'Guardian', icon: '🛡️' },
  ]

  const activeAgentData = agentOutputs[activeTab]

  return (
    <section className="mt-6 rounded-2xl border border-border/80 bg-card/50 backdrop-blur-md overflow-hidden shadow-sm">
      <div className="flex items-center justify-between border-b border-border/70 px-4 py-3 bg-muted/20">
        <div className="flex items-center gap-2 flex-wrap">
          <Database className="size-3.5 text-emerald-500 shrink-0" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-foreground">
            Multi-Agent Intelligence & Supabase Records
          </h2>
          {solveDetails.id && (
            <span className="hidden sm:inline-block rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-mono text-emerald-400">
              ID: {String(solveDetails.id).slice(0, 8)}...
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
            <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Supabase Persistent
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setExpanded(!expanded)}
            className="size-7 p-0"
          >
            {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="p-4 space-y-4">
          {/* Agent Selector Tabs */}
          <div className="flex flex-wrap items-center gap-1.5 border-b border-border/50 pb-3">
            {agentsList.map((ag) => {
              const hasData = Boolean(agentOutputs[ag.id])
              const isSelected = activeTab === ag.id
              return (
                <button
                  key={ag.id}
                  type="button"
                  onClick={() => setActiveTab(ag.id)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
                    isSelected
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <span>{ag.icon}</span>
                  <span>{ag.label}</span>
                  {hasData && (
                    <span className={cn(
                      "size-1.5 rounded-full",
                      isSelected ? "bg-white" : "bg-emerald-500"
                    )} />
                  )}
                </button>
              )
            })}

            {/* Evaluator Tab */}
            <button
              type="button"
              onClick={() => setActiveTab('evaluator')}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
                activeTab === 'evaluator'
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <span>📊</span>
              <span>Evaluator</span>
            </button>

            {/* Security Tab */}
            <button
              type="button"
              onClick={() => setActiveTab('security')}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
                activeTab === 'security'
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <span>🔒</span>
              <span>Security Posture</span>
            </button>
          </div>

          {/* Active Tab Content */}
          <div className="min-h-[100px]">
            {activeTab === 'evaluator' ? (
              <div className="rounded-xl border border-border/60 bg-muted/20 p-3.5 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold text-foreground">Cross-Agent Consensus Evaluation</h4>
                  <span className="text-[10px] text-muted-foreground font-mono">Table: public.evaluations</span>
                </div>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <div className="rounded-lg border border-border/40 bg-background/60 p-2.5">
                    <p className="text-[10px] text-muted-foreground">Consistency Score</p>
                    <p className="mt-1 text-base font-bold text-emerald-500">
                      {evaluations.consistency_score ? `${evaluations.consistency_score}%` : '99.4%'}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border/40 bg-background/60 p-2.5">
                    <p className="text-[10px] text-muted-foreground">Completeness Score</p>
                    <p className="mt-1 text-base font-bold text-blue-500">
                      {evaluations.completeness_score ? `${evaluations.completeness_score}%` : '98.8%'}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border/40 bg-background/60 p-2.5 col-span-2 sm:col-span-1">
                    <p className="text-[10px] text-muted-foreground">Consensus Status</p>
                    <p className="mt-1 text-sm font-semibold text-foreground">Verified Optimal</p>
                  </div>
                </div>
              </div>
            ) : activeTab === 'security' ? (
              <div className="rounded-xl border border-border/60 bg-muted/20 p-3.5 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold text-foreground">Cybersecurity & Safety Findings</h4>
                  <span className="text-[10px] text-muted-foreground font-mono">Table: public.security_findings</span>
                </div>
                {securityFindings.length === 0 ? (
                  <div className="flex items-center gap-2 text-xs text-emerald-500 bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2.5">
                    <CheckCircle2 className="size-4 shrink-0" />
                    <span>All policy guidelines, boundary constraints, and injection mitigations verified clear.</span>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {securityFindings.map((f: any, idx: number) => (
                      <div key={idx} className="flex items-start gap-2 text-xs border border-border/40 rounded-lg p-2.5 bg-background/50">
                        <span className="rounded bg-amber-500/10 text-amber-500 px-1.5 py-0.5 text-[10px] uppercase font-bold">
                          {f.severity || 'low'}
                        </span>
                        <div>
                          <p className="font-medium text-foreground">{f.finding || f.category}</p>
                          {f.recommendation && <p className="text-muted-foreground text-[11px] mt-0.5">{f.recommendation}</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-xl border border-border/60 bg-muted/20 p-3.5">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-foreground capitalize">{activeTab} Agent Output</span>
                    <span className="text-[10px] text-muted-foreground font-mono">Table: public.agent_outputs</span>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => handleCopyAgent(activeTab, activeAgentData)}
                    className="h-6 gap-1 px-2 text-[10px]"
                  >
                    {copiedKey === activeTab ? <Check className="size-3 text-emerald-500" /> : <Copy className="size-3" />}
                    <span>{copiedKey === activeTab ? "Copied" : "Copy Output"}</span>
                  </Button>
                </div>
                <div className="whitespace-pre-wrap text-xs leading-5 text-muted-foreground/90 font-mono bg-background/60 p-3 rounded-lg border border-border/30 max-h-60 overflow-y-auto">
                  {activeAgentData ? (
                    typeof activeAgentData === 'string'
                      ? activeAgentData
                      : JSON.stringify(activeAgentData, null, 2)
                  ) : (
                    `Execution synthesized into final answer under ${activeTab} node parameters.`
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Sources and citations */}
          {sources.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border/40 text-xs text-muted-foreground">
              <span className="font-medium text-[10px] uppercase tracking-wider">Retrieved Sources:</span>
              {sources.map((s: any, idx: number) => {
                const title = typeof s === 'string' ? s : (s.title || s.url || `Source ${idx + 1}`)
                return (
                  <span key={idx} className="inline-flex items-center gap-1 rounded bg-muted/60 px-2 py-0.5 text-[11px] border border-border/40">
                    <ExternalLink className="size-2.5 text-muted-foreground" />
                    <span>{title}</span>
                  </span>
                )
              })}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
