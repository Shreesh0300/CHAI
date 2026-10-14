"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { History, LoaderCircle, MessageCircle, PanelRight, Plus, Sparkles } from "lucide-react"
import { ChaiLogo } from "@/components/chai-logo"
import { AssistantSpeech } from "@/components/assistant-speech"
import { GenerationControls } from "@/components/generation-controls"
import { ScreenEdgeIllumination } from "@/components/screen-edge-illumination"
import {
  createAssistantReply,
  createConversationTitle,
  cleanConversationTitle,
  createId,
  createWorkArtifact,
  EMPTY_PROMPT_META,
  formatAttachmentPrompt,
  MODE_DETAILS,
  QUICK_PROMPTS,
  shouldOpenWorkPane,
  AGENT_DESCRIPTIONS,
  AGENT_DISPLAY_NAMES,
  FINALIZATION_AGENTS,
} from "@/components/chat-types"
import type {
  AssistantMode,
  ChatMessage,
  DomainCategory,
  PromptInputMeta,
  PromptSuggestion,
  WorkspaceLayout,
  ExecutionTrackerState,
  AgentExecutionInfo,
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
import { MarkdownContent } from "@/components/markdown-content"
import { playAssistantAudio, stopAssistantAudio } from "@/lib/assistant-audio"
import { cn } from "@/lib/utils"
import {
  saveConversation,
  saveMessage,
  updateConversationTitle,
  loadMessages,
} from "@/lib/supabase-conversations"

const API_BASE = (import.meta as any).env?.VITE_API_BASE || "http://localhost:8000"
const STORAGE_KEY_ACTIVE_CONV = "chai_active_conversation_id"
const STORAGE_KEY_SESSION_ID = "chai_session_id"
type InitStatus = "restoring" | "ready" | "error"
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
  const [category, setCategory] = useState<DomainCategory>("AUTO")
  const [layout, setLayout] = useState<WorkspaceLayout>("chat")
  const [work, setWork] = useState<ReturnType<typeof createWorkArtifact> | null>(null)
  const [conversationTitle, setConversationTitle] = useState("New chat")
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null)
  const [isResponding, setIsResponding] = useState(false)
  const [liveTrackerState, setLiveTrackerState] = useState<ExecutionTrackerState | null>(null)
  const [isChatModeResponding, setIsChatModeResponding] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const conversationIdRef = useRef<string | null>(null)
  const sessionIdRef = useRef<string>("")
  const [initStatus, setInitStatus] = useState<InitStatus>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem(STORAGE_KEY_ACTIVE_CONV)
      return saved ? "restoring" : "ready"
    }
    return "ready"
  })
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const activeRequestIdRef = useRef<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [mobilePane, setMobilePane] = useState<MobilePane>("response")
  const [isSpeechAssistantOpen, setIsSpeechAssistantOpen] = useState(false)
  const [isWakeWordIlluminated, setIsWakeWordIlluminated] = useState(false)
  const historyTriggerRef = useRef<HTMLButtonElement | null>(null)
  const responseTimer = useRef<number | null>(null)
  const isSubmittingRef = useRef(false)
  const closeHistory = useCallback(() => setHistoryOpen(false), [])

  const setActiveConversation = useCallback((id: string | null) => {
    setConversationId(id)
    conversationIdRef.current = id
    setActiveHistoryId(id)
    if (typeof window !== "undefined") {
      if (id) {
        localStorage.setItem(STORAGE_KEY_ACTIVE_CONV, id)
      } else {
        localStorage.removeItem(STORAGE_KEY_ACTIVE_CONV)
      }
    }
  }, [])

  useEffect(() => {
    if (typeof window !== "undefined") {
      let storedSessionId = localStorage.getItem("chai_session_id")
      if (!storedSessionId) {
        storedSessionId =
          typeof crypto !== "undefined" && crypto.randomUUID
            ? crypto.randomUUID()
            : `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`
        localStorage.setItem("chai_session_id", storedSessionId)
      }
      sessionIdRef.current = storedSessionId
    }

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
        abortControllerRef.current = null
      }
    }
  }, [])

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
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setIsResponding(false)
    setIsPaused(false)
    activeRequestIdRef.current = null
    isSubmittingRef.current = false
  }

  // ── Pause / Resume / Cancel handlers ──
  const handlePause = useCallback(async () => {
    const reqId = activeRequestIdRef.current
    if (!reqId || !isResponding || isPaused) return
    try {
      const res = await fetch(`${API_BASE}/api/chat/${reqId}/pause`, { method: "POST" })
      if (res.ok) setIsPaused(true)
    } catch {
      // Silently fail – controls are optimistic
    }
  }, [isResponding, isPaused])

  const handleResume = useCallback(async () => {
    const reqId = activeRequestIdRef.current
    if (!reqId || !isResponding || !isPaused) return
    try {
      const res = await fetch(`${API_BASE}/api/chat/${reqId}/resume`, { method: "POST" })
      if (res.ok) setIsPaused(false)
    } catch {
      // Silently fail
    }
  }, [isResponding, isPaused])

  const handleCancel = useCallback(async () => {
    const reqId = activeRequestIdRef.current
    if (!reqId || !isResponding) return

    // Immediately abort active fetch request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    try {
      await fetch(`${API_BASE}/api/chat/${reqId}/cancel`, { method: "POST" })
    } catch {
      // Silently fail
    }
    // Optimistically close SSE and reset state
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setIsPaused(false)
    setIsResponding(false)
    setLiveTrackerState((prev) =>
      prev ? { ...prev, status: "failed", error: "Cancelled by user", completedAt: Date.now() } : prev,
    )
    const cancelMessage: ChatMessage = {
      id: createId(),
      role: "assistant",
      content: "Generation cancelled.",
      requestId: reqId,
    }
    setMessages((current) => [...current, cancelMessage])
    setLiveTrackerState(null)
    setIsChatModeResponding(false)
    activeRequestIdRef.current = null
    isSubmittingRef.current = false
  }, [isResponding])

  // Restore conversation active immediately before browser refresh
  const restoreActiveConversation = useCallback(async () => {
    if (typeof window === "undefined") {
      setInitStatus("ready")
      return
    }

    const savedConvId = localStorage.getItem(STORAGE_KEY_ACTIVE_CONV)
    if (!savedConvId) {
      setInitStatus("ready")
      return
    }

    let effectiveSessionId = sessionIdRef.current
    if (!effectiveSessionId) {
      effectiveSessionId = localStorage.getItem(STORAGE_KEY_SESSION_ID) || ""
      if (!effectiveSessionId) {
        effectiveSessionId =
          typeof crypto !== "undefined" && crypto.randomUUID
            ? crypto.randomUUID()
            : `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`
        localStorage.setItem(STORAGE_KEY_SESSION_ID, effectiveSessionId)
      }
      sessionIdRef.current = effectiveSessionId
    }

    setInitStatus("restoring")
    setRestoreError(null)

    const headers: Record<string, string> = {}
    if (user?.id && !user.id.startsWith("guest") && user.id !== "guest_session") {
      headers["X-User-ID"] = user.id
    }
    if (effectiveSessionId) {
      headers["X-Session-ID"] = effectiveSessionId
    }

    try {
      const res = await fetch(`${API_BASE}/api/history/${savedConvId}`, { headers })
      if (res.status === 404 || res.status === 403) {
        // Conversation not found or access denied (e.g. stale ID or other user's conversation)
        console.warn(`Saved conversation ${savedConvId} not accessible, resetting to clean new chat.`)
        setActiveConversation(null)
        setMessages([])
        setConversationTitle("New chat")
        setInitStatus("ready")
        return
      }

      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`)
      }

      const data = await res.json()
      const loadedMessages: ChatMessage[] = (data.messages || []).map((m: any) => ({
        id: m.id || createId(),
        role: (m.role || "user") as MessageRole,
        content: m.content || "",
        resolved_domain: m.extra_data?.resolved_domain || m.resolved_domain,
        domain: m.extra_data?.domain || m.domain,
        selected_agents: m.extra_data?.selected_agents || m.selected_agents || [],
        requestId: m.extra_data?.request_id || m.request_id,
      }))

      setMessages(loadedMessages)
      setActiveConversation(data.id)
      setConversationTitle(cleanConversationTitle(data.title || "Conversation"))
      setLayout("chat")
      setWork(null)
      setInitStatus("ready")
    } catch (err: any) {
      console.warn("Backend history restore failed, checking Supabase...", err)
      try {
        const sbMsgs = await loadMessages(savedConvId)
        if (sbMsgs.length > 0) {
          setMessages(sbMsgs)
          setActiveConversation(savedConvId)
          const firstUser = sbMsgs.find((m) => m.role === "user")
          if (firstUser) {
            setConversationTitle(createConversationTitle(firstUser.content))
          }
          setLayout("chat")
          setWork(null)
          setInitStatus("ready")
          return
        }
      } catch {}
      setRestoreError(err?.message || "Failed to connect to backend")
      setInitStatus("error")
    }
  }, [user?.id, setActiveConversation])

  useEffect(() => {
    restoreActiveConversation()
  }, [restoreActiveConversation])

  function startNewChat() {
    cancelPendingResponse()
    setMessages([])
    setActiveConversation(null)
    setMode("ask")
    setLayout("chat")
    setWork(null)
    setSelectedAgent(null)
    setConversationTitle("New chat")
    setHistoryOpen(false)
    setMobilePane("response")
    setInitStatus("ready")
    setRestoreError(null)
  }

  function returnToCurrentConversation() {
    setMobilePane("response")
    setHistoryOpen(false)
  }

  function handleSelectSavedConversation(data: { id: string; title: string; messages: any[] }) {
    cancelPendingResponse()
    setActiveConversation(data.id)
    setSelectedAgent(null)
    setConversationTitle(cleanConversationTitle(data.title || "Conversation"))

    const loadedMessages: ChatMessage[] = (data.messages || []).map((m: any) => ({
      id: m.id || createId(),
      role: (m.role || "user") as MessageRole,
      content: m.content || "",
      resolved_domain: m.extra_data?.resolved_domain || m.resolved_domain,
      domain: m.extra_data?.domain || m.domain,
      selected_agents: m.extra_data?.selected_agents || m.selected_agents || [],
      requestId: m.extra_data?.request_id || m.request_id,
    }))

    setMessages(loadedMessages)
    setLayout("chat")
    setWork(null)
    setHistoryOpen(false)
    setMobilePane("response")
    setInitStatus("ready")
    setRestoreError(null)
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
    setActiveConversation(null)
    setMode(sample.mode)
    setLayout(sample.layout)
    setWork(sample.layout === "workspace" ? createWorkArtifact(sample.prompt) : null)
    setConversationTitle(sample.title)
    setActiveHistoryId(sample.id)
    setHistoryOpen(false)
    setMobilePane("response")
    setInitStatus("ready")
  }

  async function submitPrompt(
    rawPrompt: string,
    meta: PromptInputMeta,
    options: SubmitOptions = {},
  ): Promise<string> {
    const prompt = rawPrompt.trim() || formatAttachmentPrompt(meta.attachments)
    if (!prompt || isResponding || isSubmittingRef.current) return ""

    isSubmittingRef.current = true
    const selectedMode = options.mode ?? mode
    const fromChatPanel = options.fromChatPanel ?? false
    // Real user queries always use AnswerCanvas so the real CHAI response is never replaced by sample data
    const nextLayout: WorkspaceLayout = "chat"
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
    setWork(null)
    setHistoryOpen(false)
    setMobilePane(fromChatPanel ? "chat" : "response")
    setMessages((current) => [...current, userMessage])

    setIsResponding(true)
    setIsPaused(false)
    setSelectedAgent(null)

    const requestId =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `req_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`

    // Asynchronously persist to Supabase
    const effectiveConvoId = conversationIdRef.current || requestId
    saveConversation(effectiveConvoId, conversationTitle !== "New chat" ? conversationTitle : createConversationTitle(prompt)).catch(() => {})
    saveMessage(effectiveConvoId, "user", prompt).catch(() => {})

    activeRequestIdRef.current = requestId
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }

    const initialTracker: ExecutionTrackerState = {
      requestId,
      mode: "unknown",
      status: "running",
      agents: {},
      selectedAgents: [],
      startedAt: Date.now(),
    }
    setLiveTrackerState(initialTracker)
    setIsChatModeResponding(false)

    // Connect to SSE stream
    try {
      const sse = new EventSource(`${API_BASE}/api/chat/${requestId}/events`)
      eventSourceRef.current = sse

      sse.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.event === "conversation_title" && data.title) {
            setConversationTitle(cleanConversationTitle(data.title))
          } else if (data.event === "chat_mode_selected") {
            setIsChatModeResponding(true)
            setLiveTrackerState((prev) => (prev ? { ...prev, mode: "chat" } : prev))
          } else if (data.event === "request_started") {
            setIsChatModeResponding(false)
            setLiveTrackerState((prev) => {
              if (!prev) return prev
              const nextAgents = { ...prev.agents }
              const sel: string[] = data.selected_agents || []
              for (const a of sel) {
                if (!nextAgents[a]) {
                  nextAgents[a] = {
                    agent: a,
                    displayName: AGENT_DISPLAY_NAMES[a] || a,
                    description: AGENT_DESCRIPTIONS[a] || "",
                    status: "pending",
                    isFinalization: FINALIZATION_AGENTS.includes(a),
                  }
                }
              }
              return {
                ...prev,
                mode: "solve",
                selectedAgents: sel,
                domain: data.domain || prev.domain,
                agents: nextAgents,
              }
            })
          } else if (data.event === "agent_status") {
            setLiveTrackerState((prev) => {
              if (!prev) return prev
              const a = data.agent
              if (!a) return prev
              const existing = prev.agents[a]
              const updated: AgentExecutionInfo = {
                agent: a,
                displayName: existing?.displayName || AGENT_DISPLAY_NAMES[a] || a,
                description: existing?.description || AGENT_DESCRIPTIONS[a] || "",
                status: data.status,
                durationMs: data.duration_ms ?? existing?.durationMs,
                error: data.error ?? existing?.error,
                message: data.message ?? existing?.message,
                isFinalization: existing?.isFinalization ?? FINALIZATION_AGENTS.includes(a),
              }
              return {
                ...prev,
                mode: "solve",
                agents: {
                  ...prev.agents,
                  [a]: updated,
                },
              }
            })
          } else if (data.event === "final_answer") {
            setLiveTrackerState((prev) => {
              if (!prev) return prev
              return {
                ...prev,
                status: "completed",
                finalAnswer: data.final_answer,
                completedAt: Date.now(),
                totalDurationMs: prev.startedAt ? Date.now() - prev.startedAt : undefined,
              }
            })
            sse.close()
            if (eventSourceRef.current === sse) eventSourceRef.current = null
          } else if (data.event === "request_failed") {
            setLiveTrackerState((prev) => {
              if (!prev) return prev
              return {
                ...prev,
                status: "failed",
                error: data.error,
                completedAt: Date.now(),
              }
            })
            sse.close()
            if (eventSourceRef.current === sse) eventSourceRef.current = null
          } else if (data.event === "request_paused") {
            setIsPaused(true)
            setLiveTrackerState((prev) => (prev ? { ...prev, status: "running" } : prev))
          } else if (data.event === "request_resumed") {
            setIsPaused(false)
            setLiveTrackerState((prev) => (prev ? { ...prev, status: "running" } : prev))
          } else if (data.event === "request_cancelled") {
            setIsPaused(false)
            setIsResponding(false)
            setLiveTrackerState((prev) =>
              prev ? { ...prev, status: "failed", error: "Cancelled by user", completedAt: Date.now() } : prev,
            )
            sse.close()
            if (eventSourceRef.current === sse) eventSourceRef.current = null
          }
        } catch {
          // ignore parse errors
        }
      }

      sse.onerror = () => {
        // Fallback: network interruption does not break execution
      }
    } catch {
      // EventSource setup error fallback
    }

    try {
      const payload: Record<string, any> = {
        request_id: requestId,
        message: prompt,
        problem: prompt,
      }
      if (conversationIdRef.current) {
        payload.conversation_id = conversationIdRef.current
      }
      if (sessionIdRef.current) {
        payload.session_id = sessionIdRef.current
      }
      if (selectedMode && selectedMode !== "ask") {
        payload.mode = selectedMode
      }
      if (user?.id && !user.id.startsWith("guest") && user.id !== "guest_session") {
        payload.user_id = user.id
      }
      const chosenCategory = meta.category || category || "AUTO"
      payload.category = chosenCategory

      let res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: abortController.signal,
      })
      if (!res.ok && !abortController.signal.aborted) {
        res = await fetch(`${API_BASE}/api/solve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: abortController.signal,
        })
      }
      if (!res.ok) {
        let safeErrorMessage = "Service temporarily unavailable. Please try again."
        try {
          const errData = await res.json()
          if (errData?.detail && typeof errData.detail === "string") {
            const detailStr = errData.detail
            if (
              !detailStr.includes("Traceback") &&
              !detailStr.toLowerCase().includes("api_key") &&
              !detailStr.toLowerCase().includes("secret")
            ) {
              safeErrorMessage = detailStr
            }
          }
        } catch {
          // ignore parse error
        }
        throw new Error(safeErrorMessage)
      }
      const data = await res.json()
      if (data.title) {
        setConversationTitle(cleanConversationTitle(data.title))
      }
      if (data.conversation_id) {
        setActiveConversation(data.conversation_id)
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }

      // Prevent late responses from overwriting cancelled state
      if (abortController.signal.aborted || activeRequestIdRef.current !== requestId) {
        return ""
      }

      const rawContent =
        data.final_answer ||
        data.final_synthesized_answer ||
        data.message ||
        data.reply ||
        ""
      const content = rawContent
        ? rawContent.replace(/\\u([0-9a-fA-F]{4})/g, (_: string, hex: string) =>
            String.fromCharCode(parseInt(hex, 16))
          )
        : "CHAI completed processing but returned an empty response. Please try again."
      const resolvedDomain = data.resolved_domain || data.domain_category || data.domain || undefined

      // Snapshot multi-agent execution if this request ran the multi-agent solver
      let trackerSnapshot: ExecutionTrackerState | undefined = undefined
      if (
        data.selected_agents &&
        Array.isArray(data.selected_agents) &&
        data.selected_agents.length > 0
      ) {
        const rawAgents = liveTrackerState?.agents || {}
        const finalAgents: Record<string, AgentExecutionInfo> = { ...rawAgents }

        for (const a of data.selected_agents) {
          if (!finalAgents[a]) {
            finalAgents[a] = {
              agent: a,
              displayName: AGENT_DISPLAY_NAMES[a] || a,
              description: AGENT_DESCRIPTIONS[a] || "",
              status: "completed",
              isFinalization: FINALIZATION_AGENTS.includes(a),
            }
          } else if (finalAgents[a].status === "running" || finalAgents[a].status === "pending") {
            finalAgents[a] = {
              ...finalAgents[a],
              status: "completed",
            }
          }
        }

        const startedAt = liveTrackerState?.startedAt || Date.now()
        const completedAt = Date.now()
        trackerSnapshot = {
          requestId,
          mode: "solve",
          status: "completed",
          agents: finalAgents,
          selectedAgents: data.selected_agents,
          domain: resolvedDomain || liveTrackerState?.domain,
          finalAnswer: content,
          startedAt,
          completedAt,
          totalDurationMs: completedAt - startedAt,
        }
      }

      const assistantMessage: ChatMessage = {
        id: createId(),
        role: "assistant",
        content,
        resolved_domain: resolvedDomain,
        domain: resolvedDomain,
        selected_agents: data.selected_agents || [],
        requestId,
        executionTrackerState: trackerSnapshot,
      }
      setMessages((current) => [...current, assistantMessage])

      // Asynchronously persist assistant message to Supabase
      saveMessage(effectiveConvoId, "assistant", content).catch(() => {})
      if (data.title) {
        updateConversationTitle(effectiveConvoId, data.title).catch(() => {})
      }

      setIsResponding(false)
      setIsPaused(false)
      setLiveTrackerState(null)
      setIsChatModeResponding(false)
      activeRequestIdRef.current = null
      if (meta.isVoice && !isSpeechAssistantOpen) {
        playAssistantAudio(content, meta.language || data.language || "en")
      }
      return content
    } catch (err: any) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      // If request was aborted or superseded, do not show error message
      if (
        err?.name === "AbortError" ||
        abortController.signal.aborted ||
        activeRequestIdRef.current !== requestId
      ) {
        return ""
      }
      const errorMessage =
        err?.message && typeof err.message === "string" && err.message !== "API error"
          ? `Error: ${err.message}`
          : "CHAI encountered an error while processing your request. Please check your connection or try again."
      const assistantMessage: ChatMessage = {
        id: createId(),
        role: "assistant",
        content: errorMessage,
        requestId,
        executionTrackerState:
          liveTrackerState && liveTrackerState.mode === "solve"
            ? {
                ...liveTrackerState,
                status: "failed",
                error: errorMessage,
                completedAt: Date.now(),
              }
            : undefined,
      }
      setMessages((current) => [...current, assistantMessage])
      setIsResponding(false)
      setIsPaused(false)
      setLiveTrackerState(null)
      setIsChatModeResponding(false)
      activeRequestIdRef.current = null
      return errorMessage
    } finally {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      isSubmittingRef.current = false
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
            <ChaiLogo
              variant="full"
              size="sm"
              className="hidden sm:inline-flex shrink-0 mr-1"
            />
            <ChaiLogo
              variant="icon"
              size={28}
              className="sm:hidden shrink-0"
            />

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
                userId={user?.id}
                sessionId={sessionIdRef.current}
                triggerRef={historyTriggerRef}
                onSelectSavedConversation={handleSelectSavedConversation}
                onOpenSample={openSampleConversation}
                onReturnToCurrent={returnToCurrentConversation}
                onClose={closeHistory}
                onDeleteActiveConversation={startNewChat}
              />
            </div>
          </div>

          <div className="hidden min-w-0 flex-1 px-4 text-center md:block">
            <p className="truncate text-sm font-medium">
              {initStatus === "restoring" ? "Restoring conversation..." : cleanConversationTitle(conversationTitle)}
            </p>
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
            {initStatus === "restoring" ? (
              <div className="mx-auto flex min-h-[60vh] w-full max-w-[1180px] flex-col items-center justify-center px-4 py-12">
                <div className="flex flex-col items-center gap-3.5 text-center animate-in fade-in duration-300">
                  <div className="relative grid size-12 place-items-center rounded-2xl bg-muted/60 border border-border/70 shadow-inner">
                    <LoaderCircle className="size-6 animate-spin text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold tracking-tight text-foreground">Restoring conversation</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">Retrieving previous messages and workspace state...</p>
                  </div>
                </div>
              </div>
            ) : initStatus === "error" ? (
              <div className="mx-auto flex min-h-[60vh] w-full max-w-[480px] flex-col items-center justify-center px-4 py-12 text-center">
                <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-6 shadow-sm">
                  <p className="text-sm font-semibold text-destructive">Unable to restore conversation</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {restoreError || "There was a network error connecting to the backend service."}
                  </p>
                  <div className="mt-4 flex items-center justify-center gap-2">
                    <Button variant="outline" size="sm" onClick={restoreActiveConversation}>
                      Retry
                    </Button>
                    <Button variant="default" size="sm" onClick={startNewChat}>
                      Start new chat
                    </Button>
                  </div>
                </div>
              </div>
            ) : messages.length === 0 ? (
              <div className="mx-auto flex min-h-full w-full max-w-[1180px] flex-col items-center justify-center px-4 py-6 sm:px-7 sm:py-8">
                <ChatHero
                  suggestions={QUICK_PROMPTS}
                  onChoose={chooseSuggestion}
                  composer={
                    <>
                      <ResponseModePicker mode={mode} onChange={setMode} />
                      <AiChatInput
                        disabled={isResponding || initStatus === "restoring"}
                        category={category}
                        onCategoryChange={setCategory}
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
                isPaused={isPaused}
                onPause={handlePause}
                onResume={handleResume}
                onCancel={handleCancel}
                selectedAgent={selectedAgent}
                onSelectAgent={setSelectedAgent}
              />
            )}
          </section>

          {messages.length > 0 && (
            <ChatPanel
              messages={messages}
              mode={mode}
              isResponding={isResponding}
              category={category}
              onCategoryChange={setCategory}
              liveTrackerState={liveTrackerState}
              isChatModeResponding={isChatModeResponding}
              isPaused={isPaused}
              onPause={handlePause}
              onResume={handleResume}
              onCancel={handleCancel}
              selectedAgent={selectedAgent}
              onSelectAgent={setSelectedAgent}
              onSubmit={(value, meta) =>
                submitPrompt(value, meta, {
                  forceWorkspace: false,
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
                  { attachments: [], isVoice: true, category },
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
  isPaused = false,
  onPause,
  onResume,
  onCancel,
  selectedAgent,
  onSelectAgent,
}: {
  title: string
  messages: ChatMessage[]
  mode: AssistantMode
  isResponding: boolean
  isPaused?: boolean
  onPause?: () => void
  onResume?: () => void
  onCancel?: () => void
  selectedAgent?: string | null
  onSelectAgent?: (agentKey: string | null) => void
}) {
  const hasControls = Boolean(onPause && onResume && onCancel)
  const latestUserMessage = [...messages].reverse().find((message) => message.role === "user")
  const latestAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant")

  return (
    <article className="mx-auto w-full max-w-[1160px] px-5 py-8 sm:px-8 sm:py-10 xl:px-12">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{MODE_LABELS[mode]}</Badge>
        {latestAssistantMessage?.resolved_domain && (
          <Badge variant="secondary" className="uppercase font-mono text-[10px] tracking-wide">
            Domain: {latestAssistantMessage.resolved_domain}
          </Badge>
        )}
        <span className="text-xs text-muted-foreground">Response canvas</span>
      </div>
      <h1 className="mt-5 max-w-4xl text-balance break-words text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
        {cleanConversationTitle(title)}
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

      <section aria-label="Assistant response" className="mt-8 max-w-[88ch] space-y-6">
        {isResponding ? (
          <Marker
            role="status"
            aria-live="polite"
            className="rounded-2xl border border-border/80 bg-card px-5 py-4 text-sm"
          >
            <MarkerIcon className={mode === "agent" ? "size-5" : undefined}>
              {isPaused ? (
                <span className="size-3 rounded-full bg-amber-400" />
              ) : mode === "agent" ? (
                <ThinkingOrb
                  state="working"
                  size={20}
                  theme="auto"
                  aria-label="Agent is working"
                />
              ) : (
                <LoaderCircle aria-hidden="true" className="size-4 animate-spin text-primary" />
              )}
            </MarkerIcon>
            <MarkerContent>
              <span className="font-medium text-foreground">
                {isPaused
                  ? "Generation paused"
                  : mode === "agent"
                    ? "CHAI is coordinating your workflow..."
                    : "CHAI is analyzing your request..."}
              </span>
            </MarkerContent>
            {hasControls && (
              <GenerationControls
                isPaused={isPaused}
                onPause={onPause!}
                onResume={onResume!}
                onCancel={onCancel!}
                className="ml-auto"
              />
            )}
          </Marker>
        ) : latestAssistantMessage ? (
          <div className="space-y-4">
            {selectedAgent && (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-primary/40 bg-primary/10 px-4 py-2.5 text-xs text-primary shadow-xs animate-in fade-in slide-in-from-top-1 duration-200">
                <div className="flex items-center gap-2 min-w-0">
                  <Sparkles className="size-4 shrink-0 text-primary animate-pulse" />
                  <span className="truncate">
                    Highlighting insights contributed by{" "}
                    <strong className="font-semibold text-foreground">
                      {AGENT_DISPLAY_NAMES[selectedAgent] || selectedAgent}
                    </strong>
                  </span>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => onSelectAgent?.(null)}
                  className="h-6 shrink-0 px-2 text-[11px] text-muted-foreground hover:text-foreground hover:bg-primary/20"
                >
                  Clear highlight
                </Button>
              </div>
            )}
            <div className="break-words text-[1rem] leading-8 text-foreground sm:text-[1.05rem]">
              <MarkdownContent
                content={latestAssistantMessage.content}
                highlightedAgent={selectedAgent}
              />
            </div>
          </div>
        ) : null}
      </section>

      <div className="mt-12 flex max-w-[88ch] items-center gap-3 border-t border-border/70 pt-4 text-sm text-muted-foreground">
        <MessageCircle aria-hidden="true" className="size-4 shrink-0" />
        <p>Keep exploring in the chat panel on the right.</p>
      </div>
    </article>
  )
}
