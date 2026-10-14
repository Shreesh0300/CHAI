"use client"

import React, { useState, useEffect, useRef, useCallback } from "react"
import {
  Mic,
  MicOff,
  Send,
  ArrowLeft,
  Sparkles,
  Bot,
  ListTodo,
  Brain,
  Volume2,
  VolumeX,
  X,
  MessageSquare,
  Activity,
  Copy,
  Check,
  Maximize2,
  Minimize2,
  Share2,
  Search,
  ExternalLink,
  ChevronDown,
  Sun,
  Moon,
  Square,
  AudioWaveform,
} from "lucide-react"
import { AssistantOrb, type AssistantVoiceState } from "@/components/assistant-orb"
import { ScreenEdgeIllumination } from "@/components/screen-edge-illumination"
import {
  playAssistantAudio,
  stopAssistantAudio,
  isAssistantAudioPlaying,
  cleanTextForSpeech,
  cleanTextForDisplay,
} from "@/lib/assistant-audio"
import { useWakeWord } from "@/hooks/use-wake-word"
import { detectWakePhrase } from "@/lib/wake-word"
import { ChaiLogo } from "@/components/chai-logo"
import { cn } from "@/lib/utils"

const API_BASE = "http://localhost:8000"

export interface AssistantSpeechProps {
  onBack?: () => void
  initialPrompt?: string
  onSubmitVoicePrompt?: (prompt: string) => Promise<string | void> | void
}

type ActiveSection = "none" | "chat" | "tasks" | "agents" | "memory"

interface TaskItem {
  id: string
  title: string
  status: "completed" | "in-progress" | "queued"
  progress: number
}

interface AgentNode {
  name: string
  role: string
  status: "idle" | "active" | "standby"
  load: string
}

interface MemoryItem {
  key: string
  value: string
  category: "context" | "preference" | "session"
}

interface TranscriptEntry {
  id: string
  role: "user" | "assistant"
  text: string
  time: string
}

interface CommandResult {
  id: string
  query: string
  answer: string
  time: string
  status: "complete" | "synthesized"
  sources?: string[]
  keyPoints?: string[]
}

export function AssistantSpeech({ onBack, initialPrompt, onSubmitVoicePrompt }: AssistantSpeechProps) {
  // Theme state: defaults to dark for all, switches to light only if user explicitly selects it
  const [isDark, setIsDark] = useState(() => {
    if (typeof window === "undefined") return true
    return localStorage.getItem("chai-theme") !== "light"
  })

  useEffect(() => {
    const handleThemeChange = (e: Event) => {
      const custom = e as CustomEvent<string>
      if (custom.detail) {
        setIsDark(custom.detail !== "light")
      }
    }
    window.addEventListener("chai-theme-change", handleThemeChange as EventListener)
    return () => window.removeEventListener("chai-theme-change", handleThemeChange as EventListener)
  }, [])

  // Voice & AI States
  const [voiceState, setVoiceState] = useState<AssistantVoiceState>("idle")
  const [subtitle, setSubtitle] = useState<string>(
    "Tap mic or say \"Hey CHAI\" to start...",
  )
  const [inputValue, setInputValue] = useState("")
  const [isAudioMuted, setIsAudioMuted] = useState(false)
  const [activeSection, setActiveSection] = useState<ActiveSection>("none")

  // "Hey CHAI" Wake Word State
  const [wakeWordEnabled, setWakeWordEnabled] = useState(true)
  const [lastWakePhrase, setLastWakePhrase] = useState<string | null>(null)
  const [wakeFlashActive, setWakeFlashActive] = useState(false)

  // Push to side layout states
  const [hasExecutedCommand, setHasExecutedCommand] = useState(false)
  const [forceCenterView, setForceCenterView] = useState(false)
  const [commandResults, setCommandResults] = useState<CommandResult[]>([])
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // Real Web Audio API visualizer & Voice State Machine refs
  const [audioLevel, setAudioLevel] = useState(0)
  const [audioAnalyser, setAudioAnalyser] = useState<AnalyserNode | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const animationFrameRef = useRef<number | null>(null)
  const activeSpeechRecRef = useRef<any>(null)

  // Robust Lifecycle & Silence Coordination
  const isMountedRef = useRef(true)
  const isProcessingRef = useRef(false)
  const silenceTimerRef = useRef<NodeJS.Timeout | null>(null)
  const currentTranscriptRef = useRef("")
  const hasSpeechRef = useRef(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Silence Duration: 2.5 seconds of continuous silence after speech
  const SILENCE_TIMEOUT_MS = 2500

  // Forwarder refs to eliminate stale closures
  const startListeningRef = useRef<() => Promise<void>>(async () => {})
  const finalizeAndSubmitRef = useRef<() => void>(() => {})
  const handleProcessQueryRef = useRef<(query: string) => Promise<void>>(async () => {})
  const speakTextRef = useRef<(text: string, lang?: string) => Promise<void>>(async () => {})

  // Transcript History
  const [transcriptHistory, setTranscriptHistory] = useState<TranscriptEntry[]>([
    {
      id: "init-1",
      role: "assistant",
      text: "CHAI Voice Core initialized. Audio spectrum online. How can I assist you today?",
      time: "00:01",
    },
  ])

  // Mock Tasks, Agents, Memory for command center
  const [tasks] = useState<TaskItem[]>([
    { id: "t1", title: "Synthesizing multi-agent reasoning chain", status: "completed", progress: 100 },
    { id: "t2", title: "Monitoring live audio streaming packets", status: "in-progress", progress: 74 },
    { id: "t3", title: "Vector memory synchronization", status: "queued", progress: 20 },
  ])

  const [agents] = useState<AgentNode[]>([
    { name: "CHAI Core-01", role: "Primary Voice & Cognitive Orchestrator", status: "active", load: "34%" },
    { name: "Researcher-Alpha", role: "Real-time Knowledge Retrieval", status: "standby", load: "12%" },
    { name: "Synthesizer-Beta", role: "Code & Logic Synthesis", status: "standby", load: "8%" },
  ])

  const [memoryStore] = useState<MemoryItem[]>([
    { key: "Session Mode", value: "Futuristic Voice Command Center", category: "session" },
    { key: "Theme Mode", value: "Auto System Adaptive (Device Default)", category: "preference" },
    { key: "User Audio Locale", value: "en-US / 48kHz Stereo", category: "preference" },
    { key: "Engine Protocol", value: "WebSocket / Supabase Edge Synced", category: "context" },
  ])

  // Clear Silence Timer helper
  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
  }, [])

  // Stop All Audio Capture & Speech Recognition Hardware Tracks Cleanly
  const stopAudioCapture = useCallback(() => {
    clearSilenceTimer()

    // 1. Abort active speech recognition session immediately
    if (activeSpeechRecRef.current) {
      try {
        activeSpeechRecRef.current.onresult = null
        activeSpeechRecRef.current.onerror = null
        activeSpeechRecRef.current.onspeechend = null
        activeSpeechRecRef.current.onend = null
        activeSpeechRecRef.current.abort()
      } catch {}
      activeSpeechRecRef.current = null
    }

    // 2. Cancel audio visualizer animation frame
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }

    // 3. Stop all physical microphone tracks
    if (mediaStreamRef.current) {
      try {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop())
      } catch {}
      mediaStreamRef.current = null
    }

    // 4. Close audio context safely
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      try {
        audioContextRef.current.close().catch(() => {})
      } catch {}
      audioContextRef.current = null
    }

    setAudioAnalyser(null)
    setAudioLevel(0)
  }, [clearSilenceTimer])

  // Robust Text-to-Speech playback using project's existing TTS stream & SpeechSynthesis fallback
  const speakText = useCallback(
    async (textToSpeak: string, language?: string) => {
      if (!isMountedRef.current) return

      // Clean text to avoid speaking raw JSON, markdown, or debug info
      const cleanText = cleanTextForSpeech(textToSpeak)
      if (isAudioMuted || !cleanText) {
        setVoiceState("idle")
        setSubtitle(cleanText || "Response complete. Tap mic to speak.")
        isProcessingRef.current = false
        return
      }

      // Stop mic capture completely before TTS starts — assistant never hears itself
      stopAudioCapture()
      stopAssistantAudio()

      setVoiceState("speaking")
      setSubtitle(cleanText)

      try {
        await playAssistantAudio(cleanText, language || "en", {
          onStart: () => {
            if (!isMountedRef.current) return
            setVoiceState("speaking")
          },
          onChunkStart: (chunk) => {
            if (!isMountedRef.current) return
            setSubtitle(chunk)
          },
          onInterrupt: () => {
            if (!isMountedRef.current) return
            console.log("TTS interrupted: returning to idle")
            stopAssistantAudio()
            stopAudioCapture()
            setVoiceState("idle")
            setSubtitle("Speech stopped. Tap mic to speak.")
            isProcessingRef.current = false
          },
          onEnd: () => {
            if (!isMountedRef.current) return
            stopAudioCapture()
            isProcessingRef.current = false
            // Auto-relisten: restart mic after TTS like a real voice assistant
            if (wakeWordEnabled) {
              setVoiceState("idle")
              setSubtitle("Listening for next command...")
              setTimeout(() => {
                if (isMountedRef.current && !isProcessingRef.current && !isAssistantAudioPlaying()) {
                  startListeningRef.current?.()
                }
              }, 600)
            } else {
              setVoiceState("idle")
              setSubtitle("Response complete. Tap mic to speak.")
            }
          },
        })
      } catch (err) {
        console.warn("TTS playback error:", err)
      } finally {
        if (isMountedRef.current) {
          stopAudioCapture()
          isProcessingRef.current = false
          if (wakeWordEnabled) {
            setVoiceState("idle")
            setSubtitle("Listening for next command...")
            setTimeout(() => {
              if (isMountedRef.current && !isProcessingRef.current && !isAssistantAudioPlaying()) {
                startListeningRef.current?.()
              }
            }, 600)
          } else {
            setVoiceState("idle")
            setSubtitle("Response complete. Tap mic to speak.")
          }
        }
      }
    },
    [isAudioMuted, stopAudioCapture, wakeWordEnabled],
  )

  // Handle Processing query against CHAI multi-agent backend
  const handleProcessQuery = useCallback(
    async (queryText: string) => {
      const clean = queryText.trim()
      if (!clean) {
        isProcessingRef.current = false
        setVoiceState("idle")
        return
      }

      // Stop all mic capture and previous audio before processing
      stopAudioCapture()
      stopAssistantAudio()
      clearSilenceTimer()

      isProcessingRef.current = true
      setHasExecutedCommand(true)
      setForceCenterView(false)
      setVoiceState("thinking")
      setSubtitle("Thinking...")
      setInputValue("")

      const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })

      // Add user message to transcript
      const userEntry: TranscriptEntry = {
        id: `user-${Date.now()}`,
        role: "user",
        text: clean,
        time: timeStr,
      }
      setTranscriptHistory((prev) => [...prev, userEntry])

      const abortController = new AbortController()
      abortControllerRef.current = abortController

      try {
        let aiAnswer = ""

        if (onSubmitVoicePrompt) {
          try {
            const res = await onSubmitVoicePrompt(clean)
            if (typeof res === "string" && res) {
              aiAnswer = res
            }
          } catch (err) {
            console.warn("onSubmitVoicePrompt failed:", err)
          }
        }

        if (!aiAnswer && !abortController.signal.aborted) {
          let res = await fetch(`${API_BASE}/api/solve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ problem: clean, mode: "ask" }),
            signal: abortController.signal,
          })

          if (!res.ok) {
            res = await fetch(`${API_BASE}/api/chat`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ message: clean, problem: clean, mode: "ask" }),
              signal: abortController.signal,
            })
          }

          if (!res.ok) throw new Error("API assistant endpoint offline")

          const data = await res.json()
          const rawAnswer =
            data.final_answer ||
            data.final_synthesized_answer ||
            data.message ||
            "Task executed successfully across multi-agent nodes."
          aiAnswer = cleanTextForDisplay(
            rawAnswer.replace(/\\u([0-9a-fA-F]{4})/g, (_: string, hex: string) =>
              String.fromCharCode(parseInt(hex, 16))
            )
          )
        }

        if (!isMountedRef.current || abortController.signal.aborted) return

        const assistantEntry: TranscriptEntry = {
          id: `ai-${Date.now()}`,
          role: "assistant",
          text: aiAnswer,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        }
        setTranscriptHistory((prev) => [...prev, assistantEntry])

        const newResult: CommandResult = {
          id: `cmd-${Date.now()}`,
          query: clean,
          answer: aiAnswer,
          time: timeStr,
          status: "complete",
          sources: ["CHAI Knowledge Graph", "Live Web Synthesis"],
          keyPoints: [
            "Neural pipeline resolved problem parameters",
            "Synthesized response ready",
          ],
        }
        setCommandResults((prev) => [newResult, ...prev])

        // Automatic Text-to-Speech output
        await speakTextRef.current?.(aiAnswer)
      } catch (err: any) {
        if (!isMountedRef.current) return
        if (err.name === "AbortError" || abortController.signal.aborted) {
          console.log("Query processing cancelled")
          setVoiceState("idle")
          setSubtitle("Request cancelled. Tap mic to speak.")
          isProcessingRef.current = false
          return
        }

        console.error("Voice processing error:", err)
        const fallbackAnswer = `Analysis complete for: "${clean}". CHAI has processed your request.`
        const assistantEntry: TranscriptEntry = {
          id: `ai-${Date.now()}`,
          role: "assistant",
          text: fallbackAnswer,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        }
        setTranscriptHistory((prev) => [...prev, assistantEntry])

        setSubtitle("Backend service unavailable. Tap mic to retry.")
        setVoiceState("idle")
        isProcessingRef.current = false
      }
    },
    [onSubmitVoicePrompt, stopAudioCapture, clearSilenceTimer],
  )

  // Finalize transcript and submit exactly once
  const finalizeAndSubmit = useCallback(() => {
    if (!isMountedRef.current || isProcessingRef.current) return

    clearSilenceTimer()

    const rawTranscript = currentTranscriptRef.current.trim()
    if (!rawTranscript) {
      console.log("[Voice] Transcript is empty, ignoring submission")
      return
    }

    // Idempotency lock: prevent any duplicate submissions
    isProcessingRef.current = true

    // Stop microphone capture and speech recognition cleanly before submitting
    stopAudioCapture()

    // Detect wake phrase if present and strip prefix
    let processedQuery = rawTranscript
    const wakeMatch = detectWakePhrase(rawTranscript)
    if (wakeMatch) {
      setLastWakePhrase(wakeMatch.phrase)
      setWakeFlashActive(true)
      setTimeout(() => setWakeFlashActive(false), 2000)
      processedQuery = wakeMatch.trailingQuery || rawTranscript
    }

    const cleanQuery = processedQuery.trim()
    if (!cleanQuery) {
      isProcessingRef.current = false
      setVoiceState("idle")
      setSubtitle("Ready. Tap mic to speak.")
      return
    }

    // Transition state: listening -> thinking
    setVoiceState("thinking")
    setSubtitle("Thinking...")

    handleProcessQueryRef.current?.(cleanQuery)
  }, [stopAudioCapture, clearSilenceTimer])

  // Start Listening with Speech Recognition & 2.5s Silence Detection
  const startListening = useCallback(async () => {
    if (!isMountedRef.current || isProcessingRef.current || isAssistantAudioPlaying()) return

    // Clean up any ongoing capture
    stopAudioCapture()
    stopAssistantAudio()
    clearSilenceTimer()

    hasSpeechRef.current = false
    currentTranscriptRef.current = ""
    setVoiceState("listening")
    setSubtitle("Listening...")
    setInputValue("")

    const SpeechRecognitionClass =
      typeof window !== "undefined"
        ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
        : null

    if (!SpeechRecognitionClass) {
      console.warn("Speech recognition not supported in this browser.")
      setSubtitle("Speech recognition is not supported in this browser. Please type below.")
      setVoiceState("idle")
      return
    }

    // 1. Microphone capture for real-time visualizer
    try {
      if (navigator.mediaDevices?.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        })
        mediaStreamRef.current = stream

        const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
        if (AudioContextClass) {
          const audioCtx = new AudioContextClass()
          audioContextRef.current = audioCtx
          const source = audioCtx.createMediaStreamSource(stream)
          const analyser = audioCtx.createAnalyser()
          analyser.fftSize = 256
          analyser.smoothingTimeConstant = 0.8
          source.connect(analyser)
          setAudioAnalyser(analyser)

          const freqData = new Uint8Array(analyser.frequencyBinCount)
          const monitorAudio = () => {
            if (!isMountedRef.current || !mediaStreamRef.current) return
            analyser.getByteFrequencyData(freqData)
            let sumFreq = 0
            for (let i = 0; i < freqData.length; i++) {
              sumFreq += freqData[i]
            }
            const avgLevel = sumFreq / freqData.length / 255
            setAudioLevel(avgLevel)
            animationFrameRef.current = requestAnimationFrame(monitorAudio)
          }
          animationFrameRef.current = requestAnimationFrame(monitorAudio)
        }
      }
    } catch (err: any) {
      console.warn("Microphone access notice:", err)
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        setSubtitle("Microphone permission denied. Please allow microphone access to speak.")
        setVoiceState("idle")
        stopAudioCapture()
        return
      }
    }

    // 2. Speech recognition session
    try {
      const recognition = new SpeechRecognitionClass()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = "en-US"

      recognition.onresult = (event: any) => {
        if (!isMountedRef.current || isProcessingRef.current) return

        let interim = ""
        let final = ""
        for (let i = 0; i < event.results.length; i++) {
          const res = event.results[i]
          if (res.isFinal) {
            final += " " + (res[0]?.transcript || "")
          } else {
            interim += " " + (res[0]?.transcript || "")
          }
        }

        const combined = (final + " " + interim).replace(/\s+/g, " ").trim()
        if (combined) {
          currentTranscriptRef.current = combined
          hasSpeechRef.current = true
          setSubtitle(`"${combined}"`)
          setInputValue(combined)

          // Reset silence timer whenever new speech is detected
          clearSilenceTimer()

          // Stop listening and finalize transcript after approximately 2.5s continuous silence
          silenceTimerRef.current = setTimeout(() => {
            console.log("[SilenceDetector] 2.5s silence reached. Finalizing:", currentTranscriptRef.current)
            finalizeAndSubmitRef.current?.()
          }, SILENCE_TIMEOUT_MS)
        }
      }

      recognition.onerror = (event: any) => {
        if (!isMountedRef.current || isProcessingRef.current) return
        console.warn("Speech recognition event error:", event.error)

        if (event.error === "no-speech") {
          return
        }

        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          stopAudioCapture()
          clearSilenceTimer()
          setVoiceState("idle")
          setSubtitle("Microphone permission denied. Please allow microphone access.")
          return
        }

        if (event.error === "audio-capture") {
          stopAudioCapture()
          clearSilenceTimer()
          setVoiceState("idle")
          setSubtitle("No microphone detected. Check your audio device.")
          return
        }

        // If speech was already recognized, submit it
        if (currentTranscriptRef.current.trim()) {
          finalizeAndSubmitRef.current?.()
        } else {
          stopAudioCapture()
          clearSilenceTimer()
          setVoiceState("idle")
          setSubtitle("Speech recognition interrupted. Tap mic to retry.")
        }
      }

      recognition.onend = () => {
        if (!isMountedRef.current || isProcessingRef.current) return

        if (currentTranscriptRef.current.trim()) {
          if (!silenceTimerRef.current) {
            finalizeAndSubmitRef.current?.()
          }
          return
        }

        if (hasSpeechRef.current) {
          finalizeAndSubmitRef.current?.()
        }
      }

      recognition.start()
      activeSpeechRecRef.current = recognition
    } catch (recErr) {
      console.warn("Failed to start SpeechRecognition:", recErr)
      setSubtitle("Could not start speech recognition. Tap mic to retry.")
      setVoiceState("idle")
      stopAudioCapture()
    }
  }, [stopAudioCapture, clearSilenceTimer])

  useEffect(() => {
    speakTextRef.current = speakText
  }, [speakText])

  useEffect(() => {
    handleProcessQueryRef.current = handleProcessQuery
  }, [handleProcessQuery])

  useEffect(() => {
    finalizeAndSubmitRef.current = finalizeAndSubmit
  }, [finalizeAndSubmit])

  useEffect(() => {
    startListeningRef.current = startListening
  }, [startListening])

  // Toggle Listening State
  const toggleListening = useCallback(async () => {
    // 1. If speaking or audio playing: immediately stop TTS and return to idle
    if (voiceState === "speaking" || isAssistantAudioPlaying()) {
      stopAssistantAudio()
      stopAudioCapture()
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel()
      }
      isProcessingRef.current = false
      setVoiceState("idle")
      setSubtitle("Speech stopped. Tap mic to speak.")
      return
    }

    // 2. If thinking/processing: abort request and return to idle
    if (voiceState === "thinking" || isProcessingRef.current) {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
        abortControllerRef.current = null
      }
      isProcessingRef.current = false
      setVoiceState("idle")
      setSubtitle("Request cancelled. Tap mic to speak.")
      return
    }

    // 3. If currently listening:
    if (voiceState === "listening") {
      const currentTranscript = currentTranscriptRef.current.trim()
      // Tactile immediate submit: if user already spoke, submit immediately without waiting for 2.5s timer
      if (currentTranscript) {
        console.log("Tactile submit: user tapped mic button with active speech")
        finalizeAndSubmitRef.current?.()
        return
      }

      // No speech yet: pause listening and return to idle
      clearSilenceTimer()
      stopAudioCapture()
      setVoiceState("idle")
      setSubtitle("Microphone paused. Tap mic to speak.")
      return
    }

    // 4. If currently idle: start listening
    await startListening()
  }, [voiceState, stopAudioCapture, clearSilenceTimer, startListening])

  // ─── "Hey CHAI" Wake Word Integration ───────────────────────────────────────
  const { isWakeWordActive, wakeWordSupported, pause: pauseWakeWord, resume: resumeWakeWord } = useWakeWord({
    onWake: (result) => {
      console.log(`[WakeWord] 🎙️ WAKE DETECTED: "${result.phrase}" | Query: "${result.trailingQuery}"`)
      setLastWakePhrase(result.phrase)
      setWakeFlashActive(true)
      setTimeout(() => setWakeFlashActive(false), 2000)

      if (result.trailingQuery) {
        // User said "Hey CHAI, what is the weather?" — auto-submit the trailing query
        handleProcessQueryRef.current?.(result.trailingQuery)
      } else {
        // User only said "Hey CHAI" — activate mic and start listening
        if (voiceState === "idle" || voiceState === "listening") {
          setSubtitle('"Hey CHAI" detected! Listening for your command...')
          startListeningRef.current?.()
        }
      }
    },
    enabled: wakeWordEnabled && voiceState === "idle",
    cooldownMs: 4000,
  })

  // Pause wake word engine while main recording is active to avoid conflicts
  useEffect(() => {
    if (voiceState === "listening" || voiceState === "speaking" || voiceState === "thinking") {
      pauseWakeWord()
    } else if (voiceState === "idle" && wakeWordEnabled) {
      // Resume wake word listening when mic is idle
      resumeWakeWord()
    }
  }, [voiceState, wakeWordEnabled, pauseWakeWord, resumeWakeWord])

  useEffect(() => {
    isMountedRef.current = true

    if (initialPrompt) {
      handleProcessQuery(initialPrompt)
    } else {
      startListening()
    }

    return () => {
      isMountedRef.current = false
      clearSilenceTimer()
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      stopAssistantAudio()
      stopAudioCapture()
    }
  }, [])

  // Copy handler
  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  // Determine whether to show the split results view or center orb
  const showSplitLayout = hasExecutedCommand && !forceCenterView

  return (
    <div
      className={cn(
        "relative flex h-screen w-full flex-col overflow-hidden transition-colors duration-500 select-none",
        isDark ? "bg-[#030408] text-white" : "bg-slate-50 text-slate-900",
      )}
    >
      {/* Background Ambience adapted to theme */}
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute inset-0 [background-size:32px_32px] opacity-25",
          isDark
            ? "bg-[radial-gradient(#1a2035_1px,transparent_1px)]"
            : "bg-[radial-gradient(#cbd5e1_1px,transparent_1px)]",
        )}
      />
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute -left-48 top-1/4 h-[550px] w-[550px] rounded-full blur-[140px]",
          isDark ? "bg-cyan-500/10" : "bg-cyan-400/15",
        )}
      />
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute -right-48 bottom-1/4 h-[600px] w-[600px] rounded-full blur-[160px]",
          isDark ? "bg-fuchsia-600/10" : "bg-fuchsia-400/15",
        )}
      />

      {/* Subtle particle effect & sides light when doing speech (listening to user or assistant speaking) */}
      <ScreenEdgeIllumination
        active={voiceState === "listening" || voiceState === "speaking"}
        audioLevel={audioLevel}
        state={voiceState}
      />

      {/* TOP MINIMAL NAVIGATION BAR */}
      <header
        className={cn(
          "relative z-20 flex h-16 shrink-0 items-center justify-between px-4 sm:px-8 border-b backdrop-blur-xl transition-colors duration-300",
          isDark
            ? "border-white/8 bg-[rgba(6,8,16,0.7)] text-white"
            : "border-slate-200/80 bg-white/80 text-slate-900 shadow-xs",
        )}
      >
        <div className="flex items-center gap-3">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              aria-label="Exit voice assistant"
              className={cn(
                "flex size-9 items-center justify-center rounded-xl border transition",
                isDark
                  ? "border-white/10 bg-white/5 text-white/70 hover:bg-white/10 hover:text-white"
                  : "border-slate-200 bg-slate-100 text-slate-700 hover:bg-slate-200 hover:text-slate-900",
              )}
            >
              <ArrowLeft className="size-4" />
            </button>
          )}

          <div className="flex items-center gap-2.5">
            <ChaiLogo variant="icon" size="sm" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold tracking-wider">CHAI // VOICE CORE</span>
                <span className="inline-flex items-center gap-1 rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-medium text-cyan-500 dark:text-cyan-300">
                  <span className="size-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  {isDark ? "DARK SYSTEM" : "LIGHT SYSTEM"}
                </span>
                {/* Wake Word Status Badge */}
                <button
                  type="button"
                  onClick={() => setWakeWordEnabled(!wakeWordEnabled)}
                  title={wakeWordEnabled ? '"Hey CHAI" wake word is active — click to disable' : '"Hey CHAI" wake word is disabled — click to enable'}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-all duration-300 cursor-pointer",
                    wakeFlashActive
                      ? "border-emerald-400/80 bg-emerald-500/30 text-emerald-300 shadow-[0_0_16px_rgba(52,211,153,0.6)] scale-110"
                      : wakeWordEnabled
                      ? isDark
                        ? "border-amber-400/40 bg-amber-500/15 text-amber-400 hover:bg-amber-500/25"
                        : "border-amber-400/50 bg-amber-100 text-amber-700 hover:bg-amber-200"
                      : isDark
                      ? "border-white/10 bg-white/5 text-white/40 hover:text-white/60"
                      : "border-slate-200 bg-slate-100 text-slate-400 hover:text-slate-600",
                  )}
                >
                  <AudioWaveform className="size-3" />
                  {wakeFlashActive ? '"Hey CHAI" ✓' : wakeWordEnabled ? "Hey CHAI" : "Wake Off"}
                </button>
              </div>
              <p className={cn("text-[10px] tracking-wide", isDark ? "text-white/40" : "text-slate-400")}>
                INTELLIGENT VOICE & SEARCH ASSISTANT {wakeWordEnabled && wakeWordSupported ? '• SAY "HEY CHAI" TO ACTIVATE' : ""}
              </p>
            </div>
          </div>
        </div>

        {/* Section Navigation Pills */}
        <nav aria-label="Sections" className="hidden md:flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setActiveSection(activeSection === "chat" ? "none" : "chat")}
            className={cn(
              "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition",
              activeSection === "chat"
                ? "border-cyan-400/60 bg-cyan-500/20 text-cyan-500 dark:text-cyan-200 shadow-[0_0_12px_rgba(0,245,255,0.3)]"
                : isDark
                ? "border-white/8 bg-white/4 text-white/60 hover:border-white/15 hover:text-white"
                : "border-slate-200 bg-slate-100/80 text-slate-600 hover:bg-slate-200 hover:text-slate-900",
            )}
          >
            <MessageSquare className="size-3.5" />
            Chat Log
          </button>

          <button
            type="button"
            onClick={() => setActiveSection(activeSection === "tasks" ? "none" : "tasks")}
            className={cn(
              "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition",
              activeSection === "tasks"
                ? "border-purple-400/60 bg-purple-500/20 text-purple-500 dark:text-purple-200 shadow-[0_0_12px_rgba(168,85,247,0.3)]"
                : isDark
                ? "border-white/8 bg-white/4 text-white/60 hover:border-white/15 hover:text-white"
                : "border-slate-200 bg-slate-100/80 text-slate-600 hover:bg-slate-200 hover:text-slate-900",
            )}
          >
            <ListTodo className="size-3.5" />
            Tasks
          </button>

          <button
            type="button"
            onClick={() => setActiveSection(activeSection === "agents" ? "none" : "agents")}
            className={cn(
              "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition",
              activeSection === "agents"
                ? "border-fuchsia-400/60 bg-fuchsia-500/20 text-fuchsia-500 dark:text-fuchsia-200 shadow-[0_0_12px_rgba(255,45,135,0.3)]"
                : isDark
                ? "border-white/8 bg-white/4 text-white/60 hover:border-white/15 hover:text-white"
                : "border-slate-200 bg-slate-100/80 text-slate-600 hover:bg-slate-200 hover:text-slate-900",
            )}
          >
            <Bot className="size-3.5" />
            Agents
          </button>

          <button
            type="button"
            onClick={() => setActiveSection(activeSection === "memory" ? "none" : "memory")}
            className={cn(
              "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition",
              activeSection === "memory"
                ? "border-blue-400/60 bg-blue-500/20 text-blue-500 dark:text-blue-200 shadow-[0_0_12px_rgba(59,130,246,0.3)]"
                : isDark
                ? "border-white/8 bg-white/4 text-white/60 hover:border-white/15 hover:text-white"
                : "border-slate-200 bg-slate-100/80 text-slate-600 hover:bg-slate-200 hover:text-slate-900",
            )}
          >
            <Brain className="size-3.5" />
            Memory
          </button>
        </nav>

        {/* View Toggle & Audio Mute */}
        <div className="flex items-center gap-2">
          {hasExecutedCommand && (
            <button
              type="button"
              onClick={() => setForceCenterView(!forceCenterView)}
              title={forceCenterView ? "Switch to Side Split Results view" : "Center the AI orb"}
              className={cn(
                "hidden sm:flex items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs font-medium transition",
                isDark
                  ? "border-white/10 bg-white/5 text-white/70 hover:bg-white/10 hover:text-white"
                  : "border-slate-200 bg-slate-100 text-slate-700 hover:bg-slate-200 hover:text-slate-900",
              )}
            >
              {forceCenterView ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
              <span>{forceCenterView ? "Split Results" : "Center Orb"}</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => {
              setIsAudioMuted(!isAudioMuted)
              if (!isAudioMuted && typeof window !== "undefined" && window.speechSynthesis) {
                window.speechSynthesis.cancel()
              }
            }}
            aria-label={isAudioMuted ? "Unmute assistant voice" : "Mute assistant voice"}
            className={cn(
              "flex size-9 items-center justify-center rounded-xl border transition",
              isDark
                ? "border-white/10 bg-white/5 text-white/70 hover:bg-white/10 hover:text-white"
                : "border-slate-200 bg-slate-100 text-slate-700 hover:bg-slate-200 hover:text-slate-900",
            )}
          >
            {isAudioMuted ? <VolumeX className="size-4 text-red-400" /> : <Volume2 className="size-4 text-cyan-500" />}
          </button>

          <button
            type="button"
            onClick={() => {
              const nextDark = !isDark
              setIsDark(nextDark)
              const nextVal = nextDark ? "dark" : "light"
              localStorage.setItem("chai-theme", nextVal)
              const root = document.documentElement
              root.classList.toggle("dark", nextDark)
              root.classList.toggle("light", !nextDark)
              window.dispatchEvent(new CustomEvent("chai-theme-change", { detail: nextVal }))
            }}
            aria-label={`Switch to ${isDark ? "white / light" : "dark"} mode`}
            title={`Switch to ${isDark ? "white / light" : "dark"} mode`}
            className={cn(
              "flex size-9 items-center justify-center rounded-xl border transition",
              isDark
                ? "border-white/10 bg-white/5 text-white/70 hover:bg-white/10 hover:text-white"
                : "border-slate-200 bg-slate-100 text-slate-700 hover:bg-slate-200 hover:text-slate-900",
            )}
          >
            {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </div>
      </header>

      {/* BODY CONTENT: DUAL-PANE (SPLIT RESULTS) OR INITIAL CENTERPIECE */}
      <div className="relative flex flex-1 min-h-0 overflow-hidden">
        {showSplitLayout ? (
          // =========================================================================
          // SPLIT LAYOUT: RESULTS ON LEFT / CENTER & AI ASSISTANT ON THE RIGHT
          // =========================================================================
          <div className="flex flex-1 w-full min-h-0 flex-col lg:flex-row overflow-hidden">
            {/* LEFT / CENTER: THE RESULTS DISPLAY */}
            <section
              aria-label="Voice Command Results"
              className={cn(
                "flex-1 min-h-0 overflow-y-auto px-4 py-6 sm:px-8 sm:py-8 transition-colors",
                isDark ? "bg-[#04060b]/60" : "bg-slate-50/70",
              )}
            >
              <div className="mx-auto max-w-4xl space-y-6">
                {/* Results Header */}
                <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-border/70">
                  <div className="flex items-center gap-2">
                    <span className="flex size-7 items-center justify-center rounded-lg bg-cyan-500/15 text-cyan-500">
                      <Sparkles className="size-4" />
                    </span>
                    <div>
                      <h1 className="text-base font-bold tracking-tight">Synthesized Intelligence Results</h1>
                      <p className={cn("text-xs", isDark ? "text-white/40" : "text-slate-500")}>
                        Live multi-agent response & search stream
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-500">
                      Live Response
                    </span>
                    <span className={cn("text-xs", isDark ? "text-white/40" : "text-slate-400")}>
                      {commandResults.length} {commandResults.length === 1 ? "Query" : "Queries"}
                    </span>
                  </div>
                </div>

                {/* Primary/Latest Result Card */}
                {commandResults.length > 0 && (
                  <article
                    className={cn(
                      "rounded-2xl border p-5 sm:p-7 shadow-xl backdrop-blur-xl transition-all duration-300",
                      isDark
                        ? "border-white/12 bg-[rgba(12,16,28,0.75)] shadow-black/40"
                        : "border-slate-200 bg-white/90 shadow-slate-200/50",
                    )}
                  >
                    {/* User Prompt Tag */}
                    <div className="flex items-center justify-between gap-2 pb-3 mb-4 border-b border-border/50">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-fuchsia-500">
                          Voice Command
                        </span>
                        <span className={cn("text-xs font-semibold", isDark ? "text-white/90" : "text-slate-800")}>
                          &ldquo;{commandResults[0].query}&rdquo;
                        </span>
                      </div>
                      <span className={cn("text-[11px]", isDark ? "text-white/40" : "text-slate-400")}>
                        {commandResults[0].time}
                      </span>
                    </div>

                    {/* AI Synthesized Answer */}
                    <div className="space-y-4">
                      <div className="flex items-center gap-2 text-xs font-semibold text-cyan-500">
                        <Activity className="size-3.5" />
                        <span>CHAI Synthesizer Response</span>
                      </div>

                      <div
                        className={cn(
                          "whitespace-pre-wrap text-sm sm:text-base leading-7 sm:leading-8 font-normal",
                          isDark ? "text-white/95" : "text-slate-800",
                        )}
                      >
                        {commandResults[0].answer}
                      </div>

                      {/* Key takeaways or search insights */}
                      {commandResults[0].keyPoints && (
                        <div
                          className={cn(
                            "mt-5 rounded-xl border p-4 space-y-2",
                            isDark ? "border-cyan-500/20 bg-cyan-500/5" : "border-cyan-200 bg-cyan-50/60",
                          )}
                        >
                          <p className="text-xs font-bold uppercase tracking-wider text-cyan-500">
                            Execution Insights & Citations
                          </p>
                          <ul className="space-y-1.5 text-xs">
                            {commandResults[0].keyPoints.map((pt, i) => (
                              <li key={i} className="flex items-start gap-2">
                                <span className="size-1.5 rounded-full bg-cyan-400 mt-1.5 shrink-0" />
                                <span className={isDark ? "text-white/80" : "text-slate-700"}>{pt}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Result Actions */}
                      <div className="mt-5 flex items-center justify-between pt-4 border-t border-border/40">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleCopy(commandResults[0].id, commandResults[0].answer)}
                            className={cn(
                              "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition",
                              isDark
                                ? "border-white/10 bg-white/5 text-white/70 hover:bg-white/10 hover:text-white"
                                : "border-slate-200 bg-slate-100 text-slate-700 hover:bg-slate-200",
                            )}
                          >
                            {copiedId === commandResults[0].id ? (
                              <>
                                <Check className="size-3.5 text-emerald-400" />
                                <span>Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy className="size-3.5" />
                                <span>Copy Text</span>
                              </>
                            )}
                          </button>

                          <button
                            type="button"
                            onClick={() => speakText(commandResults[0].answer)}
                            className={cn(
                              "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition",
                              isDark
                                ? "border-white/10 bg-white/5 text-white/70 hover:bg-white/10 hover:text-white"
                                : "border-slate-200 bg-slate-100 text-slate-700 hover:bg-slate-200",
                            )}
                          >
                            <Volume2 className="size-3.5 text-cyan-400" />
                            <span>Read Out Loud</span>
                          </button>
                        </div>

                        <span className={cn("text-[11px]", isDark ? "text-white/40" : "text-slate-400")}>
                          Synthesized with multi-agent consensus
                        </span>
                      </div>
                    </div>
                  </article>
                )}

                {/* Previous Results Stream if multiple */}
                {commandResults.length > 1 && (
                  <div className="space-y-4 pt-4">
                    <h3 className={cn("text-xs font-bold uppercase tracking-wider", isDark ? "text-white/50" : "text-slate-500")}>
                      Previous Voice Queries
                    </h3>
                    {commandResults.slice(1).map((res) => (
                      <div
                        key={res.id}
                        className={cn(
                          "rounded-xl border p-4 transition",
                          isDark ? "border-white/8 bg-white/3" : "border-slate-200 bg-white/70",
                        )}
                      >
                        <div className="flex items-center justify-between text-xs mb-1.5">
                          <span className="font-semibold text-fuchsia-500">&ldquo;{res.query}&rdquo;</span>
                          <span className={cn("text-[10px]", isDark ? "text-white/40" : "text-slate-400")}>
                            {res.time}
                          </span>
                        </div>
                        <p className={cn("text-xs leading-relaxed line-clamp-3", isDark ? "text-white/80" : "text-slate-600")}>
                          {res.answer}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>

            {/* RIGHT SIDE: AI ASSISTANT SPEECH, LISTEN, SEARCH, AND ORB */}
            <aside
              aria-label="AI Assistant Voice & Search Controller"
              className={cn(
                "w-full lg:w-[390px] xl:w-[440px] shrink-0 border-t lg:border-t-0 lg:border-l flex flex-col justify-between overflow-y-auto p-4 sm:p-6 backdrop-blur-2xl transition-colors",
                isDark
                  ? "border-white/10 bg-[rgba(6,9,18,0.85)] text-white"
                  : "border-slate-200 bg-white/85 text-slate-900 shadow-xl",
              )}
            >
              {/* Top: Docked AI Assistant Orb & Live Voice Status */}
              <div className="flex flex-col items-center text-center space-y-3">
                <div className="flex items-center justify-between w-full pb-2 border-b border-border/50">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-500">
                    Voice AI Core // Docked
                  </span>
                  <span className={cn("text-[10px]", isDark ? "text-white/40" : "text-slate-400")}>
                    {voiceState.toUpperCase()}
                  </span>
                </div>

                {/* Docked Orb (Smooth scaled-down 60 FPS Canvas) */}
                <div className="relative my-2">
                  <AssistantOrb
                    state={voiceState}
                    audioLevel={audioLevel}
                    audioAnalyser={audioAnalyser}
                    size={200}
                    theme={isDark ? "dark" : "light"}
                    onClick={toggleListening}
                  />
                </div>

                {/* Voice State Pill */}
                <div
                  className={cn(
                    "flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider backdrop-blur-md transition-all",
                    voiceState === "listening"
                      ? "border-cyan-400/60 bg-cyan-500/15 text-cyan-400 shadow-[0_0_16px_rgba(0,245,255,0.4)] animate-pulse"
                      : voiceState === "thinking"
                      ? "border-purple-400/60 bg-purple-500/15 text-purple-400 shadow-[0_0_16px_rgba(168,85,247,0.4)]"
                      : voiceState === "speaking"
                      ? "border-fuchsia-400/60 bg-fuchsia-500/15 text-fuchsia-400 shadow-[0_0_16px_rgba(255,45,135,0.4)]"
                      : isDark
                      ? "border-white/10 bg-white/5 text-white/60"
                      : "border-slate-200 bg-slate-100 text-slate-600",
                  )}
                >
                  <span
                    className={cn(
                      "size-2 rounded-full",
                      voiceState === "listening"
                        ? "bg-cyan-400 animate-ping"
                        : voiceState === "thinking"
                        ? "bg-purple-400 animate-spin"
                        : voiceState === "speaking"
                        ? "bg-fuchsia-400 animate-pulse"
                        : "bg-emerald-400",
                    )}
                  />
                  <span>
                    {voiceState === "listening"
                      ? "Listening..."
                      : voiceState === "thinking"
                      ? "Thinking..."
                      : voiceState === "speaking"
                      ? "Speaking..."
                      : "Standby"}
                  </span>
                </div>

                {/* Live Transcript / Subtitle Box */}
                <div
                  className={cn(
                    "w-full rounded-xl border p-3 text-xs leading-relaxed min-h-[52px] text-center",
                    isDark ? "border-white/8 bg-white/4 text-white/80" : "border-slate-200 bg-slate-50 text-slate-700",
                  )}
                >
                  {subtitle}
                </div>

                {voiceState === "speaking" && (
                  <button
                    type="button"
                    onClick={toggleListening}
                    className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg border border-red-500/50 bg-red-500/20 py-2 text-xs font-bold text-red-400 hover:bg-red-500/30 transition shadow-[0_0_15px_rgba(239,68,68,0.35)] animate-pulse cursor-pointer"
                  >
                    <Square className="size-3 fill-current" />
                    <span>Stop Speaking (shout &ldquo;Stop&rdquo; or Esc)</span>
                  </button>
                )}
              </div>

              {/* Middle: Quick Category Shortcuts */}
              <div className="my-4 space-y-2">
                <span className={cn("text-[10px] font-bold uppercase tracking-wider block", isDark ? "text-white/40" : "text-slate-400")}>
                  Voice Follow-ups
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    "Deepen research citations",
                    "Synthesize agent code",
                    "Verify vector memory",
                  ].map((chip, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleProcessQuery(chip)}
                      className={cn(
                        "rounded-lg border px-2.5 py-1 text-[11px] transition text-left",
                        isDark
                          ? "border-white/8 bg-white/3 text-white/70 hover:border-cyan-400/40 hover:text-white"
                          : "border-slate-200 bg-slate-100/70 text-slate-600 hover:border-cyan-500 hover:text-slate-900",
                      )}
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              </div>

              {/* Bottom: Futuristic Search & Voice Command Input Bar */}
              <div className="pt-2">
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    if (inputValue.trim()) handleProcessQuery(inputValue)
                  }}
                  className={cn(
                    "flex items-center gap-1.5 rounded-xl border p-1.5 transition-all",
                    isDark
                      ? "border-white/12 bg-[rgba(10,13,24,0.85)] shadow-lg"
                      : "border-slate-300 bg-white shadow-md",
                  )}
                >
                  <button
                    type="button"
                    onClick={toggleListening}
                    aria-label={voiceState === "listening" ? "Stop microphone" : "Speak to CHAI"}
                    className={cn(
                      "flex size-9 shrink-0 items-center justify-center rounded-lg border transition-all duration-300",
                      voiceState === "listening"
                        ? "border-cyan-400 bg-gradient-to-tr from-cyan-500 to-fuchsia-500 text-white shadow-[0_0_18px_rgba(0,245,255,0.7)] animate-pulse"
                        : isDark
                        ? "border-white/10 bg-white/5 text-white/70 hover:border-cyan-400/50 hover:text-white"
                        : "border-slate-200 bg-slate-100 text-slate-600 hover:text-slate-900",
                    )}
                  >
                    {voiceState === "listening" ? <MicOff className="size-4" /> : <Mic className="size-4" />}
                  </button>

                  <input
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    placeholder={
                      voiceState === "listening"
                        ? "Listening... speak now"
                        : "Voice search or command..."
                    }
                    className={cn(
                      "flex-1 bg-transparent px-2 text-xs outline-none",
                      isDark ? "text-white placeholder-white/40" : "text-slate-900 placeholder-slate-400",
                    )}
                  />

                  <button
                    type="submit"
                    disabled={!inputValue.trim() || voiceState === "thinking"}
                    aria-label="Send query"
                    className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-tr from-cyan-400 via-indigo-500 to-fuchsia-500 text-white shadow-[0_0_12px_rgba(0,245,255,0.35)] transition disabled:opacity-30 hover:scale-105 active:scale-95"
                  >
                    <Send className="size-3.5" />
                  </button>
                </form>

                <p className={cn("mt-1.5 text-center text-[10px]", isDark ? "text-white/30" : "text-slate-400")}>
                  Tap mic or speak &quot;Hey CHAI&quot; to command
                </p>
              </div>
            </aside>
          </div>
        ) : (
          // =========================================================================
          // INITIAL CENTERPIECE LAYOUT: LARGE CENTERED AI ORB BEFORE FIRST COMMAND
          // =========================================================================
          <main className="relative flex flex-1 flex-col items-center justify-center px-4 py-6">
            {/* Telemetry Status Line above Orb */}
            <div
              className={cn(
                "mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em]",
                isDark ? "text-white/50" : "text-slate-500",
              )}
            >
              <Activity className="size-3 text-cyan-500" />
              <span>SYS.AUDIO // {voiceState === "idle" ? "STANDBY" : voiceState.toUpperCase()}</span>
              <span className="opacity-30">|</span>
              <span className="text-cyan-500">{voiceState === "speaking" ? "TTS ACTIVE" : "WEBAUDIO 48KHZ"}</span>
            </div>

            {/* The Centerpiece AI Core Orb */}
            <div className="relative flex items-center justify-center">
              <AssistantOrb
                state={voiceState}
                audioLevel={audioLevel}
                audioAnalyser={audioAnalyser}
                size={340}
                theme={isDark ? "dark" : "light"}
                onClick={toggleListening}
              />
            </div>

            {/* Status Pill below Orb */}
            <div className="mt-5 flex items-center gap-2">
              <div
                className={cn(
                  "flex items-center gap-2 rounded-full border px-4 py-1 text-xs font-semibold uppercase tracking-wider backdrop-blur-md transition-all duration-300",
                  voiceState === "listening"
                    ? "border-cyan-400/60 bg-cyan-500/15 text-cyan-400 shadow-[0_0_20px_rgba(0,245,255,0.4)] animate-pulse"
                    : voiceState === "thinking"
                    ? "border-purple-400/60 bg-purple-500/15 text-purple-400 shadow-[0_0_20px_rgba(168,85,247,0.4)]"
                    : voiceState === "speaking"
                    ? "border-fuchsia-400/60 bg-fuchsia-500/15 text-fuchsia-400 shadow-[0_0_20px_rgba(255,45,135,0.4)]"
                    : isDark
                    ? "border-white/10 bg-white/5 text-white/60"
                    : "border-slate-200 bg-white text-slate-600 shadow-xs",
                )}
              >
                <span
                  className={cn(
                    "size-2 rounded-full",
                    voiceState === "listening"
                      ? "bg-cyan-400 animate-ping"
                      : voiceState === "thinking"
                      ? "bg-purple-400 animate-spin"
                      : voiceState === "speaking"
                      ? "bg-fuchsia-400 animate-pulse"
                      : "bg-emerald-400",
                  )}
                />
                <span>
                  {voiceState === "listening"
                    ? "Listening..."
                    : voiceState === "thinking"
                    ? "Thinking..."
                    : voiceState === "speaking"
                    ? "Speaking..."
                    : "Idle Core"}
                </span>
              </div>
            </div>

            {/* Voice Transcript / Subtitle Display */}
            <div className="mt-4 w-full max-w-xl text-center px-4">
              <p
                className={cn(
                  "min-h-[44px] text-balance text-sm sm:text-base font-medium leading-relaxed transition-all duration-300",
                  isDark ? "text-white/90" : "text-slate-800",
                )}
              >
                {subtitle}
              </p>

              {voiceState === "speaking" && (
                <div className="mt-3 flex items-center justify-center">
                  <button
                    type="button"
                    onClick={toggleListening}
                    className="flex items-center gap-2 rounded-xl border border-red-500/50 bg-red-500/20 px-5 py-2.5 text-xs font-bold uppercase tracking-wider text-red-400 hover:bg-red-500/30 transition shadow-[0_0_20px_rgba(239,68,68,0.4)] animate-pulse cursor-pointer"
                  >
                    <Square className="size-3.5 fill-current" />
                    <span>Stop Speaking (shout &ldquo;Stop&rdquo; or press Esc)</span>
                  </button>
                </div>
              )}
            </div>

            {/* Quick Voice Command Chips */}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              {[
                "Analyze current system architecture",
                "Synthesize deep research report",
                "Generate AI voice workflow",
              ].map((prompt, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleProcessQuery(prompt)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-[11px] transition",
                    isDark
                      ? "border-white/8 bg-white/4 text-white/60 hover:border-cyan-400/40 hover:text-white"
                      : "border-slate-200 bg-white text-slate-600 shadow-xs hover:border-cyan-500 hover:text-slate-900",
                  )}
                >
                  {prompt}
                </button>
              ))}
            </div>

            {/* Bottom Command Dock in Center Mode */}
            <div className="w-full max-w-2xl px-4 mt-8">
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (inputValue.trim()) handleProcessQuery(inputValue)
                }}
                className={cn(
                  "flex items-center gap-2 rounded-2xl border p-2 shadow-2xl backdrop-blur-2xl transition-colors",
                  isDark
                    ? "border-white/12 bg-[rgba(10,13,24,0.78)] shadow-black/50"
                    : "border-slate-200 bg-white/90 shadow-slate-200/50",
                )}
              >
                <button
                  type="button"
                  onClick={toggleListening}
                  aria-label={voiceState === "listening" ? "Stop microphone" : "Activate voice assistant"}
                  className={cn(
                    "flex size-11 shrink-0 items-center justify-center rounded-xl border transition-all duration-300",
                    voiceState === "listening"
                      ? "border-cyan-400 bg-gradient-to-tr from-cyan-500 to-fuchsia-500 text-white shadow-[0_0_24px_rgba(0,245,255,0.7)] animate-pulse"
                      : isDark
                      ? "border-white/10 bg-white/5 text-white/70 hover:border-cyan-400/50 hover:text-white"
                      : "border-slate-200 bg-slate-100 text-slate-700 hover:border-cyan-500 hover:text-slate-900",
                  )}
                >
                  {voiceState === "listening" ? <MicOff className="size-5" /> : <Mic className="size-5" />}
                </button>

                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder={
                    voiceState === "listening"
                      ? "Listening... (or type your query here)"
                      : "Transmit a command or ask CHAI anything..."
                  }
                  className={cn(
                    "flex-1 bg-transparent px-3 text-sm outline-none",
                    isDark ? "text-white placeholder-white/40" : "text-slate-900 placeholder-slate-400",
                  )}
                />

                <button
                  type="submit"
                  disabled={!inputValue.trim() || voiceState === "thinking"}
                  aria-label="Send command"
                  className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-cyan-400 via-indigo-500 to-fuchsia-500 text-white shadow-[0_0_16px_rgba(0,245,255,0.35)] transition disabled:opacity-30 hover:scale-105 active:scale-95"
                >
                  <Send className="size-4" />
                </button>
              </form>
            </div>
          </main>
        )}
      </div>

      {/* OVERLAY DRAWER FOR SECTIONS (Chat Log, Tasks, Agents, Memory) */}
      {activeSection !== "none" && (
        <aside
          aria-label={`${activeSection.toUpperCase()} Overview`}
          className={cn(
            "fixed inset-y-0 right-0 z-50 w-full max-w-md border-l p-6 shadow-2xl backdrop-blur-3xl animate-in slide-in-from-right duration-300 flex flex-col",
            isDark
              ? "border-white/12 bg-[rgba(8,10,20,0.95)] text-white"
              : "border-slate-200 bg-white/95 text-slate-900",
          )}
        >
          <div className="flex items-center justify-between pb-4 border-b border-border/60">
            <div className="flex items-center gap-2">
              {activeSection === "chat" && <MessageSquare className="size-4 text-cyan-500" />}
              {activeSection === "tasks" && <ListTodo className="size-4 text-purple-500" />}
              {activeSection === "agents" && <Bot className="size-4 text-fuchsia-500" />}
              {activeSection === "memory" && <Brain className="size-4 text-blue-500" />}
              <h2 className="text-sm font-bold uppercase tracking-wider">
                {activeSection} Console
              </h2>
            </div>
            <button
              type="button"
              onClick={() => setActiveSection("none")}
              className={cn(
                "flex size-8 items-center justify-center rounded-lg border transition",
                isDark
                  ? "border-white/10 bg-white/5 text-white/70 hover:text-white"
                  : "border-slate-200 bg-slate-100 text-slate-700 hover:text-slate-900",
              )}
            >
              <X className="size-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto py-4 space-y-3">
            {/* CHAT LOG SECTION */}
            {activeSection === "chat" && (
              <div className="space-y-3">
                {transcriptHistory.map((item) => (
                  <div
                    key={item.id}
                    className={cn(
                      "rounded-xl border p-3 text-xs leading-relaxed",
                      item.role === "user"
                        ? isDark
                          ? "border-fuchsia-500/30 bg-fuchsia-500/10 text-fuchsia-100 ml-6"
                          : "border-fuchsia-300 bg-fuchsia-50 text-fuchsia-900 ml-6"
                        : isDark
                        ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-100 mr-6"
                        : "border-cyan-300 bg-cyan-50 text-cyan-900 mr-6",
                    )}
                  >
                    <div className="flex items-center justify-between mb-1 text-[10px] opacity-60">
                      <span>{item.role === "user" ? "USER TRANSMISSION" : "CHAI VOICE CORE"}</span>
                      <span>{item.time}</span>
                    </div>
                    <p>{item.text}</p>
                  </div>
                ))}
              </div>
            )}

            {/* TASKS SECTION */}
            {activeSection === "tasks" && (
              <div className="space-y-3">
                {tasks.map((task) => (
                  <div
                    key={task.id}
                    className={cn(
                      "rounded-xl border p-3.5 space-y-2",
                      isDark ? "border-white/10 bg-white/5" : "border-slate-200 bg-slate-50",
                    )}
                  >
                    <div className="flex items-center justify-between text-xs font-semibold">
                      <span>{task.title}</span>
                      <span className="text-[10px] uppercase text-cyan-500">{task.status}</span>
                    </div>
                    <div className={cn("w-full h-1.5 rounded-full overflow-hidden", isDark ? "bg-white/10" : "bg-slate-200")}>
                      <div
                        className="h-full bg-gradient-to-r from-cyan-400 to-fuchsia-500 rounded-full"
                        style={{ width: `${task.progress}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* AGENTS SECTION */}
            {activeSection === "agents" && (
              <div className="space-y-3">
                {agents.map((agent, i) => (
                  <div
                    key={i}
                    className={cn(
                      "rounded-xl border p-3.5 flex items-center justify-between",
                      isDark ? "border-white/10 bg-white/5" : "border-slate-200 bg-slate-50",
                    )}
                  >
                    <div className="space-y-0.5">
                      <p className="text-xs font-bold">{agent.name}</p>
                      <p className={cn("text-[10px]", isDark ? "text-white/50" : "text-slate-500")}>{agent.role}</p>
                    </div>
                    <div className="text-right">
                      <span className="inline-block px-2 py-0.5 rounded-full text-[9px] font-semibold bg-emerald-500/20 text-emerald-500 border border-emerald-500/30">
                        {agent.status}
                      </span>
                      <p className={cn("text-[10px] mt-1", isDark ? "text-white/40" : "text-slate-400")}>
                        Load: {agent.load}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* MEMORY SECTION */}
            {activeSection === "memory" && (
              <div className="space-y-3">
                {memoryStore.map((mem, i) => (
                  <div
                    key={i}
                    className={cn(
                      "rounded-xl border p-3 text-xs flex flex-col gap-1",
                      isDark ? "border-white/10 bg-white/5" : "border-slate-200 bg-slate-50",
                    )}
                  >
                    <div className="flex items-center justify-between text-[10px] opacity-60 uppercase">
                      <span>{mem.category}</span>
                      <span className="text-cyan-500">SYNCED</span>
                    </div>
                    <span className="font-semibold">{mem.key}</span>
                    <span className={cn(isDark ? "text-white/60" : "text-slate-600")}>{mem.value}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      )}
    </div>
  )
}
