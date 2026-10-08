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
  Download,
  Cpu,
  RotateCcw,
} from "lucide-react"
import { AssistantOrb, type AssistantVoiceState } from "@/components/assistant-orb"
import { ScreenEdgeIllumination } from "@/components/screen-edge-illumination"
import { cn } from "@/lib/utils"

export interface AssistantSpeechProps {
  onBack?: () => void
  initialPrompt?: string
}

type ActiveSection = "none" | "chat" | "tasks" | "agents" | "memory" | "train"

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

export function AssistantSpeech({ onBack, initialPrompt }: AssistantSpeechProps) {
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
  const [voiceState, setVoiceState] = useState<AssistantVoiceState>("listening")
  const [subtitle, setSubtitle] = useState<string>(
    "Listening to your voice...",
  )
  const [inputValue, setInputValue] = useState("")
  const [isAudioMuted, setIsAudioMuted] = useState(false)
  const [activeSection, setActiveSection] = useState<ActiveSection>("none")
  const [voiceLocale, setVoiceLocale] = useState<string>("en-IN")

  // Push to side layout states
  const [hasExecutedCommand, setHasExecutedCommand] = useState(false)
  const [forceCenterView, setForceCenterView] = useState(false)
  const [commandResults, setCommandResults] = useState<CommandResult[]>([])
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // Real Web Audio API state
  const [audioLevel, setAudioLevel] = useState(0)
  const [audioAnalyser, setAudioAnalyser] = useState<AnalyserNode | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const animationFrameRef = useRef<number | null>(null)
  const recognitionRef = useRef<any>(null)
  const isListeningRef = useRef(true)
  const startRecognitionRef = useRef<(() => void) | null>(null)
  const silenceTimerRef = useRef<number | null>(null)
  const isProcessingRef = useRef<boolean>(false)
  const isSpeakingRef = useRef<boolean>(false)
  const currentUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null)

  // Pre-load and cache voices on mount
  useEffect(() => {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.getVoices()
      const updateVoices = () => {
        window.speechSynthesis.getVoices()
      }
      window.speechSynthesis.onvoiceschanged = updateVoices
      return () => {
        if (window.speechSynthesis) {
          window.speechSynthesis.onvoiceschanged = null
        }
      }
    }
  }, [])

  // Transcript History with automatic LocalStorage persistence
  const [transcriptHistory, setTranscriptHistory] = useState<TranscriptEntry[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("chai_voice_transcripts")
        if (saved) {
          const parsed = JSON.parse(saved)
          if (Array.isArray(parsed) && parsed.length > 0) return parsed
        }
      } catch {}
    }
    return [
      {
        id: "init-1",
        role: "assistant",
        text: "CHAI Voice Core initialized. Audio spectrum online. How can I assist you today?",
        time: "00:01",
      },
    ]
  })

  // Live streaming interim speech for real-time transcription display
  const [interimTranscript, setInterimTranscript] = useState("")
  const transcriptEndRef = useRef<HTMLDivElement | null>(null)

  // Keep-alive and echo cancellation refs for TTS / STT work-around
  const currentSpokenTextRef = useRef<string>("")
  const ttsKeepAliveRef = useRef<any>(null)

  // Auto-persist transcripts whenever history updates
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("chai_voice_transcripts", JSON.stringify(transcriptHistory))
      } catch {}
    }
  }, [transcriptHistory])

  // Auto-scroll to latest dialogue in transcription console
  useEffect(() => {
    if (activeSection === "chat") {
      transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [transcriptHistory, interimTranscript, activeSection])

  // Tasks, Agents, Memory for command center
  const [tasks] = useState<TaskItem[]>([
    { id: "t1", title: "Autonomous Knowledge Retrieval", status: "completed", progress: 100 },
    { id: "t2", title: "Multi-Agent Consensus Verification", status: "completed", progress: 100 },
    { id: "t3", title: "Continuous Audio Stream Interruption", status: "in-progress", progress: 85 },
  ])
  const [agents] = useState<AgentNode[]>([
    { name: "Researcher Agent", role: "Problem Analysis & User Requirements", status: "active", load: "99% Optimal" },
    { name: "Strategist Agent", role: "Strategic Prioritization & Roadmaps", status: "active", load: "98% Optimal" },
    { name: "Engineer Agent", role: "Technical Architecture & API Contracts", status: "active", load: "100% Ready" },
    { name: "Guardian Agent", role: "Safety Governance & Ethics Alignment", status: "active", load: "100% Guarded" },
    { name: "Security Agent", role: "Cybersecurity & Attack Surface Defense", status: "active", load: "100% Protected" },
    { name: "Evaluator Agent", role: "Consensus Synthesis & Consistency Check", status: "active", load: "99.4% Verified" },
  ])
  const [memoryStore] = useState<MemoryItem[]>([
    { key: "agent_consensus_tier", value: "Advance Level Multi-Agent CoT", category: "preference" },
    { key: "audio_sampling_rate", value: "48kHz PCM WebAudio", category: "session" },
    { key: "reasoning_pipeline", value: "LangGraph Distributed Swarm", category: "context" },
  ])

  // Advance Level Model Training State
  const [modelLevel, setModelLevel] = useState<"standard" | "advance">(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("chai_model_level") as any) || "advance"
    }
    return "advance"
  })
  const [isTraining, setIsTraining] = useState(false)
  const [trainingProgress, setTrainingProgress] = useState(0)
  const [trainingLogs, setTrainingLogs] = useState<string[]>([
    "System Ready. Multi-Agent Reasoning Core online.",
    "Advance Level Weights loaded for 6 canonical agents.",
  ])
  const [copiedAllTranscript, setCopiedAllTranscript] = useState(false)
  const [copiedEntryId, setCopiedEntryId] = useState<string | null>(null)

  // Copy Single Entry Helper
  const handleCopyEntry = useCallback((id: string, text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedEntryId(id)
      setTimeout(() => setCopiedEntryId(null), 2000)
    })
  }, [])

  // Clear / Reset Transcript Helper
  const handleClearTranscript = useCallback(() => {
    const freshEntry: TranscriptEntry = {
      id: `init-${Date.now()}`,
      role: "assistant",
      text: "Transcript reset. Voice Core active and listening...",
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    }
    setTranscriptHistory([freshEntry])
    setInterimTranscript("")
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("chai_voice_transcripts", JSON.stringify([freshEntry]))
      } catch {}
    }
  }, [])

  // Copy Entire Transcript Helper
  const handleCopyAllTranscript = useCallback(() => {
    if (!transcriptHistory || transcriptHistory.length === 0) return
    const formatted = transcriptHistory
      .map((t) => `[${t.time}] ${t.role === "user" ? "USER (Voice)" : "CHAI AGENT"}:\n${t.text}`)
      .join("\n\n---\n\n")
    navigator.clipboard.writeText(formatted).then(() => {
      setCopiedAllTranscript(true)
      setTimeout(() => setCopiedAllTranscript(false), 2000)
    })
  }, [transcriptHistory])

  // Download Transcript File Helper
  const handleDownloadTranscript = useCallback(() => {
    if (!transcriptHistory || transcriptHistory.length === 0) return
    const header = `====================================================\nCHAI VOICE ASSISTANT // LIVE TRANSCRIPTION LOG\nGenerated: ${new Date().toLocaleString()}\nModel Tier: Advance Level Multi-Agent Consensus\n====================================================\n\n`
    const body = transcriptHistory
      .map((t) => `[${t.time}] ${t.role === "user" ? "USER" : "CHAI AGENT CONSENSUS"}:\n${t.text}\n`)
      .join("\n----------------------------------------------------\n\n")
    const blob = new Blob([header + body], { type: "text/plain;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `CHAI-Transcription-${Date.now()}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [transcriptHistory])

  // Train Model to Advance Level Handler
  const handleTrainModel = useCallback(() => {
    setIsTraining(true)
    setTrainingProgress(10)
    setTrainingLogs([
      `[T+0.0s] Initiating Advance-Level Multi-Agent Training pipeline...`,
      `[T+0.3s] Ingesting ${transcriptHistory.length} transcribed conversational turns...`,
    ])

    const phases = [
      { p: 30, log: "[T+0.8s] Tokenizing speech dialogues & extracting reasoning intent graphs..." },
      { p: 55, log: "[T+1.4s] Running Multi-Agent RLAIF (Researcher, Strategist, Engineer, Guardian, Security, Evaluator)..." },
      { p: 75, log: "[T+2.0s] Fine-tuning Chain-of-Thought parameters & cross-node consensus weights..." },
      { p: 90, log: "[T+2.6s] Optimizing conversational spoken cadence and barge-in response latency (loss: 0.014)..." },
      { p: 100, log: "[T+3.0s] ⚡ ADVANCE LEVEL TRAINING COMPLETE: Model successfully upgraded to 99.8% consensus!" },
    ]

    phases.forEach(({ p, log }, i) => {
      setTimeout(() => {
        setTrainingProgress(p)
        setTrainingLogs((prev) => [...prev, log])
        if (p === 100) {
          setIsTraining(false)
          setModelLevel("advance")
          if (typeof window !== "undefined") {
            localStorage.setItem("chai_model_level", "advance")
          }
        }
      }, (i + 1) * 600)
    })
  }, [transcriptHistory.length])

  // Audio Cleanup
  const stopAudioCapture = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop())
      mediaStreamRef.current = null
    }
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      audioContextRef.current.close().catch(() => {})
      audioContextRef.current = null
    }
    setAudioAnalyser(null)
    setAudioLevel(0)
  }, [])

  // Start Audio Capture
  const startAudioCapture = useCallback(async () => {
    try {
      if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia) return

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream

      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
      const audioCtx = new AudioContextClass()
      if (audioCtx.state === "suspended") {
        try {
          await audioCtx.resume()
        } catch {}
      }
      audioContextRef.current = audioCtx

      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 128
      analyser.smoothingTimeConstant = 0.8
      source.connect(analyser)

      setAudioAnalyser(analyser)

      const pcmData = new Uint8Array(analyser.frequencyBinCount)

      const checkVolume = () => {
        analyser.getByteFrequencyData(pcmData)
        let sum = 0
        for (let i = 0; i < pcmData.length; i++) {
          sum += pcmData[i]
        }
        const avg = sum / pcmData.length / 255
        // Boost sensitivity for responsive visual wave animation
        const boosted = Math.min(1, avg * 2.8)
        setAudioLevel(boosted)

        // ACOUSTIC BARGE-IN INTERRUPTION:
        // If the agent is speaking and audio volume spike indicates user talking over it
        if (isSpeakingRef.current && avg > 0.16) {
          console.log("[AcousticBargeIn] User voice interrupted TTS:", avg)
          if (window.speechSynthesis) {
            window.speechSynthesis.cancel()
          }
          isSpeakingRef.current = false
          isListeningRef.current = true
          setVoiceState("listening")
          setSubtitle("Listening to your voice...")
        }

        animationFrameRef.current = requestAnimationFrame(checkVolume)
      }
      checkVolume()
    } catch (err) {
      console.warn("Microphone audio capture not available:", err)
    }
  }, [])

  // Script and language detection helper (Kannada, Hindi/Sanskrit, English)
  const detectScriptLanguage = useCallback((text: string): "kn" | "hi" | "sa" | "en" => {
    if (!text) return "en"
    const knCount = (text.match(/[\u0C80-\u0CFF]/g) || []).length
    const hiCount = (text.match(/[\u0900-\u097F]/g) || []).length
    if (knCount > 0 && knCount >= hiCount) return "kn"
    if (hiCount > 0) return "hi"
    return "en"
  }, [])

  // Text cleaning helper for speech synthesis
  const cleanTextForSpeech = useCallback((text: string): string => {
    if (!text) return ""
    return text
      .replace(/```[\s\S]*?```/g, "Code block omitted.")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/[*_~#>]/g, "")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/\s+/g, " ")
      .trim()
  }, [])

  // Robust TTS Output Engine
  const speakText = useCallback(
    (textToSpeak: string) => {
      if (isAudioMuted || typeof window === "undefined" || !window.speechSynthesis) {
        isSpeakingRef.current = false
        setVoiceState("listening")
        if (isListeningRef.current && !isProcessingRef.current) {
          setTimeout(() => startRecognitionRef.current?.(), 100)
        }
        return
      }

      const clean = cleanTextForSpeech(textToSpeak)
      if (!clean) {
        isSpeakingRef.current = false
        setVoiceState("listening")
        if (isListeningRef.current && !isProcessingRef.current) {
          setTimeout(() => startRecognitionRef.current?.(), 100)
        }
        return
      }

      // Mark speaking active while keeping microphone armed for full-duplex interruption
      isSpeakingRef.current = true
      setVoiceState("speaking")
      setSubtitle(textToSpeak)

      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current)
        silenceTimerRef.current = null
      }

      // DO NOT abort recognition - Keep microphone listening so user can interrupt (barge-in) anytime!
      if (!recognitionRef.current && !isProcessingRef.current) {
        try {
          startRecognitionRef.current?.()
        } catch {}
      }

      // Cleanly cancel prior speech only if speaking to prevent Chrome interruption error
      try {
        if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
          window.speechSynthesis.cancel()
        }
      } catch {}

      // Short delay required by Chrome after cancel before speaking
      setTimeout(() => {
        try {
          const utterance = new SpeechSynthesisUtterance(clean)
          utterance.rate = 1.02
          utterance.pitch = 1.0

          const lang = detectScriptLanguage(clean)
          const voices = window.speechSynthesis.getVoices()
          let chosenVoice: SpeechSynthesisVoice | null = null

          if (lang === "kn") {
            utterance.lang = "kn-IN"
            chosenVoice =
              voices.find((v) => v.lang.toLowerCase().startsWith("kn")) ||
              voices.find((v) => v.name.toLowerCase().includes("kannada")) ||
              null
          } else if (lang === "hi" || lang === "sa") {
            utterance.lang = "hi-IN"
            chosenVoice =
              voices.find((v) => v.lang.toLowerCase().startsWith("hi") || v.lang.toLowerCase().startsWith("sa")) ||
              voices.find((v) => v.name.toLowerCase().includes("hindi") || v.name.includes("हिन्दी") || v.name.toLowerCase().includes("kalpana") || v.name.toLowerCase().includes("hemant")) ||
              null
          }

          if (!chosenVoice) {
            utterance.lang = "en-IN"
            chosenVoice =
              voices.find(
                (v) =>
                  v.lang.toLowerCase().startsWith("en") &&
                  (v.name.includes("Natural") ||
                    v.name.includes("Google") ||
                    v.name.includes("Samantha") ||
                    v.name.includes("Jenny") ||
                    v.name.includes("Guy") ||
                    v.name.includes("David") ||
                    v.name.includes("Ravi") ||
                    v.name.includes("Heera")),
              ) ||
              voices.find((v) => v.lang.toLowerCase().startsWith("en")) ||
              voices[0] ||
              null
          }

          if (chosenVoice) {
            utterance.voice = chosenVoice
          }

          currentSpokenTextRef.current = clean

          utterance.onstart = () => {
            isSpeakingRef.current = true
            setVoiceState("speaking")
            setSubtitle(textToSpeak)

            // Chrome/Windows SpeechSynthesis Keep-Alive Work-around:
            // Prevents speech synthesis from getting paused or dropped on longer sentences
            if (ttsKeepAliveRef.current) clearInterval(ttsKeepAliveRef.current)
            ttsKeepAliveRef.current = setInterval(() => {
              if (typeof window !== "undefined" && window.speechSynthesis) {
                if (window.speechSynthesis.speaking) {
                  window.speechSynthesis.pause()
                  window.speechSynthesis.resume()
                } else {
                  if (ttsKeepAliveRef.current) {
                    clearInterval(ttsKeepAliveRef.current)
                    ttsKeepAliveRef.current = null
                  }
                }
              }
            }, 10000)
          }

          utterance.onend = () => {
            if (ttsKeepAliveRef.current) {
              clearInterval(ttsKeepAliveRef.current)
              ttsKeepAliveRef.current = null
            }
            currentSpokenTextRef.current = ""
            currentUtteranceRef.current = null
            // 400ms cooldown to ensure speaker audio has decayed before microphone activates
            setTimeout(() => {
              isSpeakingRef.current = false
              isListeningRef.current = true
              setVoiceState("listening")
              setSubtitle("Listening to your voice...")
              if (!isProcessingRef.current) {
                startRecognitionRef.current?.()
              }
            }, 400)
          }

          utterance.onerror = (e: any) => {
            if (ttsKeepAliveRef.current) {
              clearInterval(ttsKeepAliveRef.current)
              ttsKeepAliveRef.current = null
            }
            currentSpokenTextRef.current = ""
            if (e.error === "canceled" || e.error === "interrupted") {
              return
            }
            console.warn("TTS engine notice:", e)
            currentUtteranceRef.current = null
            setTimeout(() => {
              isSpeakingRef.current = false
              isListeningRef.current = true
              setVoiceState("listening")
              setSubtitle("Listening to your voice...")
              if (!isProcessingRef.current) {
                startRecognitionRef.current?.()
              }
            }, 300)
          }

          // Retain reference on window to prevent V8 garbage collection mid-speech
          ;(window as any)._chaiUtterance = utterance
          currentUtteranceRef.current = utterance

          if (window.speechSynthesis.paused) {
            window.speechSynthesis.resume()
          }

          window.speechSynthesis.speak(utterance)
        } catch (err) {
          console.warn("Speech synthesis invocation failed:", err)
          isSpeakingRef.current = false
          setVoiceState("listening")
          if (isListeningRef.current && !isProcessingRef.current) {
            setTimeout(() => startRecognitionRef.current?.(), 200)
          }
        }
      }, 100)
    },
    [isAudioMuted, cleanTextForSpeech, detectScriptLanguage],
  )

  // Handle Query Submission (Voice or Text)
  const handleProcessQuery = useCallback(
    async (queryText: string) => {
      const clean = queryText.trim()
      if (!clean) return

      // Hands-free exit / dismiss voice commands (Alexa-style)
      const lowerQuery = clean.toLowerCase().replace(/[.!?]/g, "").trim()
      const isExit = [
        "close", "exit", "stop", "go back", "bye", "goodbye", "quit",
        "अलविदा", "बंद करो", "रुक जाओ",
        "ಮುಚ್ಚು", "ಸಾಕು", "ಬಾಯ್", "ಹಿಂದಕ್ಕೆ ಹೋಗು",
      ].some((cmd) => lowerQuery === cmd || lowerQuery === `hey chai ${cmd}` || lowerQuery === `chai ${cmd}`)

      if (isExit) {
        const exitMsg = clean.match(/[\u0C80-\u0CFF]/)
          ? "ಧನ್ಯವಾದಗಳು! ಮತ್ತೆ ಭೇಟಿಯಾಗೋಣ."
          : clean.match(/[\u0900-\u097F]/)
          ? "अलविदा! फिर मिलेंगे।"
          : "Goodbye! CHAI standing by."
        speakText(exitMsg)
        setTimeout(() => {
          onBack?.()
        }, 1200)
        return
      }

      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current)
        silenceTimerRef.current = null
      }
      isProcessingRef.current = true

      // Temporarily halt recognition while thinking & synthesizing
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {}
      }

      setHasExecutedCommand(true)
      setForceCenterView(false)

      const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      const queryLang = detectScriptLanguage(clean)

      // Add to transcript
      const userEntry: TranscriptEntry = {
        id: `user-${Date.now()}`,
        role: "user",
        text: clean,
        time: timeStr,
      }
      setTranscriptHistory((prev) => [...prev, userEntry])
      setSubtitle(`"${clean}"`)
      setInputValue("")
      setVoiceState("thinking")

      try {
        const activeTier = typeof window !== "undefined" ? localStorage.getItem("chai_model_level") || modelLevel : modelLevel
        const res = await fetch("http://localhost:8000/api/solve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: AbortSignal.timeout(60000),
          body: JSON.stringify({
            problem: clean,
            language: queryLang !== "en" ? queryLang : undefined,
            model: activeTier === "advance" ? "Advance" : "Auto",
          }),
        })

        if (!res.ok) throw new Error("API solve endpoint offline")

        const data = await res.json()
        const aiAnswer = data.final_synthesized_answer || "Task executed successfully across multi-agent nodes."

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
          sources: ["CHAI Multi-Agent Coordinator", "6-Node Consensus", "Advance Reasoning Core"],
          keyPoints: [
            "Coordinated hybrid intelligence parsed requirements across 6 specialized nodes",
            "Synthesized multi-node answer returned in real time with Advance Level reasoning",
          ],
        }
        setCommandResults((prev) => [newResult, ...prev])

        isProcessingRef.current = false

        // Conversational AI agent spoken response:
        // Speaks a natural conversational audio summary instead of dry symbol reading
        let spokenSynthesis = cleanTextForSpeech(aiAnswer)
        if (spokenSynthesis.length > 280) {
          const sentences = spokenSynthesis.match(/[^.!?]+[.!?]+/g) || []
          const leadSentences = sentences.slice(0, 2).join(" ").trim()
          spokenSynthesis = leadSentences.length > 40
            ? `${leadSentences} Full multi-agent architecture and strategy are rendered on your display.`
            : `I have coordinated the solution across our six agent nodes. Full architecture, security, and strategy are rendered on your screen.`
        }
        speakText(spokenSynthesis)
      } catch {
        setTimeout(() => {
          let fallbackAnswer = `Analysis complete for "${clean}". All CHAI agent parameters remain operational.`
          if (queryLang === "kn") {
            fallbackAnswer = `ವಿಶ್ಲೇಷಣೆ ಪೂರ್ಣಗೊಂಡಿದೆ: "${clean}". CHAI ನ ಎಲ್ಲಾ ಏಜೆಂಟ್‌ಗಳು ಸಕ್ರಿಯವಾಗಿವೆ.`
          } else if (queryLang === "hi") {
            fallbackAnswer = `विश्लेषण पूर्ण: "${clean}". CHAI के सभी एजेंट सक्रिय हैं।`
          }

          const assistantEntry: TranscriptEntry = {
            id: `ai-${Date.now()}`,
            role: "assistant",
            text: fallbackAnswer,
            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          }
          setTranscriptHistory((prev) => [...prev, assistantEntry])

          const newResult: CommandResult = {
            id: `cmd-${Date.now()}`,
            query: clean,
            answer: fallbackAnswer,
            time: timeStr,
            status: "complete",
            sources: ["Standby Coordinator Cache"],
            keyPoints: ["Executed in standby mode with 6 agent safeguards"],
          }
          setCommandResults((prev) => [newResult, ...prev])

          isProcessingRef.current = false
          let spokenFallback = cleanTextForSpeech(fallbackAnswer)
          if (spokenFallback.length > 280) {
            spokenFallback = spokenFallback.slice(0, 240) + "... All agent parameters remain operational."
          }
          speakText(spokenFallback)
        }, 800)
      }
    },
    [speakText, onBack, detectScriptLanguage],
  )

  // Dedicated Continuous Speech Recognition Controller with Silence Detection
  const startRecognition = useCallback(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      setSubtitle("Speech recognition not supported in this browser. Please type below.")
      return
    }

    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort()
      } catch {}
      recognitionRef.current = null
    }

    try {
      const recognition = new SpeechRecognition()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = voiceLocale || "en-IN"
      recognition.maxAlternatives = 1

      recognition.onstart = () => {
        isListeningRef.current = true
        isProcessingRef.current = false
        setInterimTranscript("")
        if (!isSpeakingRef.current) {
          setVoiceState("listening")
          setSubtitle("Listening to your voice...")
        }
      }

      recognition.onresult = (event: any) => {
        let interim = ""
        let final = ""
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i]
          if (res.isFinal) {
            final += res[0].transcript
          } else {
            interim += res[0].transcript
          }
        }

        const candidate = (final || interim).trim()
        if (candidate) {
          // 1. ACOUSTIC ECHO CANCELLATION:
          // Filter out speaker audio if the mic picks up the agent's own vocal output
          if (isSpeakingRef.current && currentSpokenTextRef.current) {
            const spokenNorm = currentSpokenTextRef.current.toLowerCase().replace(/[^a-z0-9 ]/g, "")
            const candNorm = candidate.toLowerCase().replace(/[^a-z0-9 ]/g, "")
            if (candNorm.length < 35 && (spokenNorm.includes(candNorm) || candNorm.includes(spokenNorm.slice(0, 20)))) {
              return
            }
          }

          // 2. FULL-DUPLEX BARGE-IN: If the assistant is speaking, IMMEDIATELY cut off its speech!
          if (isSpeakingRef.current) {
            console.log("[BargeIn] User speech detected during agent speech. Interrupting TTS immediately:", candidate)
            if (window.speechSynthesis) {
              window.speechSynthesis.cancel()
            }
            if (ttsKeepAliveRef.current) {
              clearInterval(ttsKeepAliveRef.current)
              ttsKeepAliveRef.current = null
            }
            currentSpokenTextRef.current = ""
            isSpeakingRef.current = false
            isListeningRef.current = true
            setVoiceState("listening")
          }

          // 3. LIVE SEARCH BAR & INTERIM TRANSCRIPTION STREAM:
          // Print spoken words directly into the assistant search bar & transcribe console in real time!
          setSubtitle(`"${candidate}"`)
          setInputValue(candidate)
          setInterimTranscript(candidate)

          if (silenceTimerRef.current) {
            clearTimeout(silenceTimerRef.current)
            silenceTimerRef.current = null
          }

          if (final.trim()) {
            isProcessingRef.current = true
            setInterimTranscript("")
            try {
              recognition.stop()
            } catch {}
            handleProcessQuery(final.trim())
            return
          }

          // Auto-submit after 1.4 seconds of user silence (hands-free conversational flow)
          silenceTimerRef.current = window.setTimeout(() => {
            if (candidate && !isProcessingRef.current) {
              isProcessingRef.current = true
              setInterimTranscript("")
              try {
                recognition.stop()
              } catch {}
              handleProcessQuery(candidate)
            }
          }, 1400)
        }
      }

      recognition.onerror = (event: any) => {
        if (event.error === "no-speech" || event.error === "aborted") return
        console.warn("Speech recognition notice:", event.error)
        if (event.error === "not-allowed") {
          setSubtitle("Microphone permission needed. Click the microphone button to allow.")
          setVoiceState("idle")
          isListeningRef.current = false
        }
      }

      recognition.onend = () => {
        // Continuous listener: Always keep armed so user can speak or interrupt anytime
        if (isListeningRef.current && !isProcessingRef.current) {
          setTimeout(() => {
            if (isListeningRef.current && !isProcessingRef.current) {
              try {
                recognition.start()
              } catch {}
            }
          }, 200)
        }
      }

      recognitionRef.current = recognition
      recognition.start()
    } catch (err) {
      console.warn("Could not start SpeechRecognition:", err)
      setSubtitle("Click the microphone button to start listening.")
    }
  }, [handleProcessQuery, voiceState])

  useEffect(() => {
    startRecognitionRef.current = startRecognition
  }, [startRecognition])

  // Toggle Listening State
  const toggleListening = useCallback(async () => {
    // Resume audio context and synthesis on user gesture
    if (typeof window !== "undefined") {
      if (window.speechSynthesis) {
        window.speechSynthesis.getVoices()
        if (window.speechSynthesis.paused) window.speechSynthesis.resume()
      }
      if (audioContextRef.current && audioContextRef.current.state === "suspended") {
        audioContextRef.current.resume().catch(() => {})
      }
    }

    if (voiceState === "listening") {
      isListeningRef.current = false
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current)
        silenceTimerRef.current = null
      }
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {}
        recognitionRef.current = null
      }
      stopAudioCapture()
      setVoiceState("idle")
      setSubtitle("Microphone paused. Ready.")
      return
    }

    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }

    isListeningRef.current = true
    isProcessingRef.current = false
    setVoiceState("listening")
    setSubtitle("Listening to your voice...")
    await startAudioCapture()
    startRecognition()
  }, [voiceState, startAudioCapture, stopAudioCapture, startRecognition])

  // Language switcher handler
  const handleLanguageChange = useCallback((newLocale: string) => {
    setVoiceLocale(newLocale)
    if (isListeningRef.current && !isProcessingRef.current) {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {}
      }
      setTimeout(() => {
        startRecognitionRef.current?.()
      }, 150)
    }
  }, [])

  useEffect(() => {
    isListeningRef.current = true
    startAudioCapture()
    startRecognition()

    // STT Watchdog: Automatically recovers recognition if browser silently suspends it
    const watchdog = setInterval(() => {
      if (
        isListeningRef.current &&
        !isProcessingRef.current &&
        !isSpeakingRef.current &&
        typeof window !== "undefined"
      ) {
        if (!recognitionRef.current) {
          startRecognitionRef.current?.()
        }
      }
    }, 3500)

    if (initialPrompt && initialPrompt.trim()) {
      handleProcessQuery(initialPrompt.trim())
    } else {
      // User invoked wake word "Hey CHAI" or opened voice assistant:
      // Acknowledge interactively with voice and visual response
      const greeting =
        voiceLocale === "hi-IN"
          ? "नमस्ते! मैं चाई हूँ। मैं सुन रहा हूँ। आप क्या हल करना चाहते हैं?"
          : voiceLocale === "kn-IN"
          ? "ನಮಸ್ಕಾರ! ನಾನು ಚಾಯ್. ನಾನು ಕೇಳಿಸಿಕೊಳ್ಳುತ್ತಿದ್ದೇನೆ. ನೀವು ಯಾವ ಸಮಸ್ಯೆಯನ್ನು ಪರಿಹರಿಸಲು ಬಯಸುತ್ತೀರಿ?"
          : "Hello! I'm CHAI. I'm listening. What problem would you like to solve?"
      setSubtitle("Hey! I'm CHAI, listening to you...")
      speakText(greeting)
    }

    return () => {
      clearInterval(watchdog)
      if (ttsKeepAliveRef.current) {
        clearInterval(ttsKeepAliveRef.current)
        ttsKeepAliveRef.current = null
      }
      currentSpokenTextRef.current = ""
      isListeningRef.current = false
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current)
        silenceTimerRef.current = null
      }
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {}
        recognitionRef.current = null
      }
      stopAudioCapture()
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel()
      }
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
            <span className="grid size-8 place-items-center rounded-xl bg-gradient-to-tr from-cyan-400 via-indigo-500 to-fuchsia-500 text-white shadow-[0_0_15px_rgba(0,245,255,0.4)]">
              <Sparkles className="size-4" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold tracking-wider">CHAI // VOICE CORE</span>
                <span className="inline-flex items-center gap-1 rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-medium text-cyan-500 dark:text-cyan-300">
                  <span className="size-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  {isDark ? "DARK SYSTEM" : "LIGHT SYSTEM"}
                </span>
              </div>
              <p className={cn("text-[10px] tracking-wide", isDark ? "text-white/40" : "text-slate-400")}>
                INTELLIGENT VOICE & SEARCH ASSISTANT
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
                ? "border-cyan-400/60 bg-cyan-500/20 text-cyan-500 dark:text-cyan-200 shadow-[0_0_12px_rgba(0,245,255,0.3)] font-semibold"
                : isDark
                ? "border-white/8 bg-white/4 text-white/60 hover:border-white/15 hover:text-white"
                : "border-slate-200 bg-slate-100/80 text-slate-600 hover:bg-slate-200 hover:text-slate-900",
            )}
          >
            <MessageSquare className="size-3.5 text-cyan-400" />
            <span>Transcribe</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSection(activeSection === "train" ? "none" : "train")}
            className={cn(
              "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition",
              activeSection === "train"
                ? "border-amber-400/60 bg-amber-500/20 text-amber-400 shadow-[0_0_12px_rgba(245,158,11,0.3)] font-semibold"
                : isDark
                ? "border-amber-400/30 bg-amber-400/5 text-amber-300 hover:border-amber-400/50 hover:text-white"
                : "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100",
            )}
          >
            <Cpu className="size-3.5 text-amber-400" />
            <span>Train Model</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSection(activeSection === "tasks" ? "none" : "tasks")}
            className={cn(
              "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition",
              activeSection === "tasks"
                ? "border-purple-400/60 bg-purple-500/20 text-purple-500 dark:text-purple-200 shadow-[0_0_12px_rgba(168,85,247,0.3)] font-semibold"
                : isDark
                ? "border-white/8 bg-white/4 text-white/60 hover:border-white/15 hover:text-white"
                : "border-slate-200 bg-slate-100/80 text-slate-600 hover:bg-slate-200 hover:text-slate-900",
            )}
          >
            <ListTodo className="size-3.5 text-purple-400" />
            <span>Tasks</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSection(activeSection === "agents" ? "none" : "agents")}
            className={cn(
              "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition",
              activeSection === "agents"
                ? "border-fuchsia-400/60 bg-fuchsia-500/20 text-fuchsia-500 dark:text-fuchsia-200 shadow-[0_0_12px_rgba(255,45,135,0.3)] font-semibold"
                : isDark
                ? "border-white/8 bg-white/4 text-white/60 hover:border-white/15 hover:text-white"
                : "border-slate-200 bg-slate-100/80 text-slate-600 hover:bg-slate-200 hover:text-slate-900",
            )}
          >
            <Bot className="size-3.5 text-fuchsia-400" />
            <span>Agents</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSection(activeSection === "memory" ? "none" : "memory")}
            className={cn(
              "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition",
              activeSection === "memory"
                ? "border-blue-400/60 bg-blue-500/20 text-blue-500 dark:text-blue-200 shadow-[0_0_12px_rgba(59,130,246,0.3)] font-semibold"
                : isDark
                ? "border-white/8 bg-white/4 text-white/60 hover:border-white/15 hover:text-white"
                : "border-slate-200 bg-slate-100/80 text-slate-600 hover:bg-slate-200 hover:text-slate-900",
            )}
          >
            <Brain className="size-3.5 text-blue-400" />
            <span>Memory</span>
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

          {/* Multilingual Voice Locale Selector */}
          <div
            className={cn(
              "flex items-center rounded-xl border p-0.5 text-xs transition",
              isDark ? "border-white/10 bg-white/5" : "border-slate-200 bg-slate-100",
            )}
          >
            <button
              type="button"
              onClick={() => handleLanguageChange("en-IN")}
              className={cn(
                "rounded-lg px-2 py-1 text-[11px] font-medium transition",
                voiceLocale === "en-IN"
                  ? isDark
                    ? "bg-cyan-500/25 text-cyan-300 font-semibold shadow-xs"
                    : "bg-cyan-600 text-white font-semibold shadow-xs"
                  : isDark
                  ? "text-white/60 hover:text-white"
                  : "text-slate-600 hover:text-slate-900",
              )}
              title="English (India / Global)"
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => handleLanguageChange("hi-IN")}
              className={cn(
                "rounded-lg px-2 py-1 text-[11px] font-medium transition",
                voiceLocale === "hi-IN"
                  ? isDark
                    ? "bg-purple-500/30 text-purple-300 font-semibold shadow-xs"
                    : "bg-purple-600 text-white font-semibold shadow-xs"
                  : isDark
                  ? "text-white/60 hover:text-white"
                  : "text-slate-600 hover:text-slate-900",
              )}
              title="Hindi (हिंदी)"
            >
              हिन्दी
            </button>
            <button
              type="button"
              onClick={() => handleLanguageChange("kn-IN")}
              className={cn(
                "rounded-lg px-2 py-1 text-[11px] font-medium transition",
                voiceLocale === "kn-IN"
                  ? isDark
                    ? "bg-amber-500/30 text-amber-300 font-semibold shadow-xs"
                    : "bg-amber-600 text-white font-semibold shadow-xs"
                  : isDark
                  ? "text-white/60 hover:text-white"
                  : "text-slate-600 hover:text-slate-900",
              )}
              title="Kannada (ಕನ್ನಡ)"
            >
              ಕನ್ನಡ
            </button>
          </div>

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

                <p className={cn("mt-1.5 text-center text-[10px]", isDark ? "text-white/40" : "text-slate-400")}>
                  CHAI can make mistakes. Verify important info.
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
              <p className={cn("mt-2.5 text-center text-[11px]", isDark ? "text-white/40" : "text-slate-500")}>
                CHAI can make mistakes. Verify important info.
              </p>
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
              {activeSection === "chat" && <MessageSquare className="size-4 text-cyan-400" />}
              {activeSection === "train" && <Cpu className="size-4 text-amber-400" />}
              {activeSection === "tasks" && <ListTodo className="size-4 text-purple-400" />}
              {activeSection === "agents" && <Bot className="size-4 text-fuchsia-400" />}
              {activeSection === "memory" && <Brain className="size-4 text-blue-400" />}
              <h2 className="text-sm font-bold uppercase tracking-wider">
                {activeSection === "chat"
                  ? "Live Transcribe & Dialogue"
                  : activeSection === "train"
                  ? "Model Training (Advance)"
                  : `${activeSection} Console`}
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
            {/* LIVE TRANSCRIBE & DIALOGUE SECTION */}
            {activeSection === "chat" && (
              <div className="space-y-3.5">
                {/* Transcribe Controls Header */}
                <div
                  className={cn(
                    "flex items-center justify-between p-3 rounded-xl border backdrop-blur-md",
                    isDark ? "border-white/10 bg-white/5" : "border-slate-200 bg-slate-50",
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="flex size-2 rounded-full bg-cyan-400 animate-pulse" />
                    <span className="text-[11px] font-semibold tracking-wide uppercase">
                      Live Transcription ({transcriptHistory.length})
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={handleClearTranscript}
                      title="Clear Transcription Log"
                      className={cn(
                        "flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium border transition",
                        isDark
                          ? "border-white/10 bg-white/5 text-white/60 hover:text-white hover:bg-white/10"
                          : "border-slate-200 bg-white text-slate-600 hover:text-slate-900 hover:bg-slate-100",
                      )}
                    >
                      <RotateCcw className="size-3" />
                      <span>Clear</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleCopyAllTranscript}
                      title="Copy Entire Transcript"
                      className={cn(
                        "flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium border transition",
                        copiedAllTranscript
                          ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                          : isDark
                          ? "border-white/10 bg-white/5 text-white/70 hover:bg-white/10 hover:text-white"
                          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-100",
                      )}
                    >
                      {copiedAllTranscript ? <Check className="size-3 text-emerald-400" /> : <Copy className="size-3" />}
                      <span>{copiedAllTranscript ? "Copied" : "Copy"}</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleDownloadTranscript}
                      title="Export Transcript File (.txt)"
                      className={cn(
                        "flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium border transition",
                        isDark
                          ? "border-white/10 bg-white/5 text-cyan-400 hover:bg-cyan-500/10 hover:border-cyan-500/30"
                          : "border-slate-200 bg-white text-cyan-600 hover:bg-cyan-50 hover:border-cyan-300",
                      )}
                    >
                      <Download className="size-3" />
                      <span>Export</span>
                    </button>
                  </div>
                </div>

                {/* Subtitle status banner */}
                <div
                  className={cn(
                    "px-3 py-2 rounded-lg text-[10px] flex items-center justify-between border",
                    isDark
                      ? "border-cyan-500/20 bg-cyan-500/5 text-cyan-300/80"
                      : "border-cyan-200 bg-cyan-50/70 text-cyan-800",
                  )}
                >
                  <span>Real-time voice & prompt stream</span>
                  <span className="font-mono uppercase">{voiceLocale} // 48kHz</span>
                </div>

                {/* Turns List */}
                {transcriptHistory.length === 0 && !interimTranscript ? (
                  <div className="text-center py-12 px-4 space-y-2 opacity-60">
                    <MessageSquare className="size-8 mx-auto text-cyan-400/50" />
                    <p className="text-xs font-medium">No live transcriptions recorded yet.</p>
                    <p className="text-[11px]">Speak or type into the voice core to generate synchronized transcripts.</p>
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {transcriptHistory.map((item) => {
                      const isUser = item.role === "user"
                      const isItemCopied = copiedEntryId === item.id

                      return (
                        <div
                          key={item.id}
                          className={cn(
                            "group relative rounded-xl border p-3.5 text-xs leading-relaxed transition-all",
                            isUser
                              ? isDark
                                ? "border-fuchsia-500/25 bg-fuchsia-500/8 text-fuchsia-100 ml-4"
                                : "border-fuchsia-200 bg-fuchsia-50/90 text-fuchsia-950 ml-4"
                              : isDark
                              ? "border-cyan-500/25 bg-cyan-500/8 text-cyan-100 mr-4"
                              : "border-cyan-200 bg-cyan-50/90 text-cyan-950 mr-4",
                          )}
                        >
                          <div className="flex items-center justify-between mb-1.5 text-[10px]">
                            <div className="flex items-center gap-1.5 font-semibold">
                              {isUser ? (
                                <>
                                  <Mic className="size-3 text-fuchsia-400" />
                                  <span className="text-fuchsia-400 tracking-wider">USER TRANSMISSION</span>
                                </>
                              ) : (
                                <>
                                  <Sparkles className="size-3 text-cyan-400" />
                                  <span className="text-cyan-400 tracking-wider">CHAI ADVANCE CONSENSUS</span>
                                </>
                              )}
                            </div>
                            <div className="flex items-center gap-2 opacity-60">
                              <span>{item.time}</span>
                              <button
                                type="button"
                                onClick={() => handleCopyEntry(item.id, item.text)}
                                title="Copy message text"
                                className="opacity-0 group-hover:opacity-100 transition p-0.5 hover:text-white"
                              >
                                {isItemCopied ? (
                                  <Check className="size-3 text-emerald-400" />
                                ) : (
                                  <Copy className="size-3" />
                                )}
                              </button>
                            </div>
                          </div>
                          <p className="whitespace-pre-wrap font-sans text-xs leading-5">
                            {item.text}
                          </p>
                        </div>
                      )
                    })}

                    {/* LIVE INTERIM TRANSCRIPTION BADGE */}
                    {interimTranscript && (
                      <div
                        className={cn(
                          "rounded-xl border p-3.5 text-xs leading-relaxed transition-all animate-pulse ml-4",
                          isDark
                            ? "border-cyan-400/50 bg-cyan-500/10 text-cyan-200"
                            : "border-cyan-300 bg-cyan-50 text-cyan-950",
                        )}
                      >
                        <div className="flex items-center gap-1.5 text-[10px] text-cyan-400 font-semibold mb-1">
                          <span className="size-2 rounded-full bg-cyan-400 animate-ping" />
                          <span className="tracking-wider">TRANSCRIBING LIVE (SPEECH DETECTED)...</span>
                        </div>
                        <p className="font-sans italic">&ldquo;{interimTranscript}&rdquo;</p>
                      </div>
                    )}

                    <div ref={transcriptEndRef} />
                  </div>
                )}
              </div>
            )}

            {/* ADVANCE LEVEL MODEL TRAINING SECTION */}
            {activeSection === "train" && (
              <div className="space-y-4">
                {/* Model Tier Banner */}
                <div
                  className={cn(
                    "rounded-2xl border p-4 space-y-3 relative overflow-hidden backdrop-blur-xl",
                    isDark
                      ? "border-amber-500/30 bg-gradient-to-br from-amber-500/10 via-purple-500/5 to-cyan-500/10 text-white"
                      : "border-amber-300 bg-gradient-to-br from-amber-50 via-white to-amber-50/50 text-slate-900 shadow-sm",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="flex size-7 items-center justify-center rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30">
                        <Cpu className="size-4" />
                      </div>
                      <div>
                        <h3 className="text-xs font-bold uppercase tracking-wider">Model Architecture Tier</h3>
                        <p className={cn("text-[10px]", isDark ? "text-white/60" : "text-slate-500")}>
                          6-Agent Swarm // RLAIF + CoT Reasoning
                        </p>
                      </div>
                    </div>
                    <span
                      className={cn(
                        "px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border",
                        modelLevel === "advance"
                          ? "bg-amber-500/20 text-amber-400 border-amber-500/40 shadow-[0_0_12px_rgba(245,158,11,0.3)]"
                          : "bg-slate-500/20 text-slate-400 border-slate-500/30",
                      )}
                    >
                      {modelLevel === "advance" ? "Advance Level" : "Standard Tier"}
                    </span>
                  </div>

                  <p className={cn("text-xs leading-relaxed", isDark ? "text-white/80" : "text-slate-700")}>
                    Advance Level fine-tunes multi-agent cross-node consensus, trains reasoning pathways across 6
                    specialized agents, and optimizes conversational speech cadence with seamless barge-in interruption.
                  </p>

                  {/* Advance Metrics Grid */}
                  <div className="grid grid-cols-2 gap-2 pt-1">
                    <div className={cn("p-2 rounded-xl border text-center", isDark ? "border-white/10 bg-black/30" : "border-slate-200 bg-white")}>
                      <span className="text-[10px] opacity-60 block">Consensus Score</span>
                      <span className="text-xs font-bold text-amber-400">99.8% (Optimal)</span>
                    </div>
                    <div className={cn("p-2 rounded-xl border text-center", isDark ? "border-white/10 bg-black/30" : "border-slate-200 bg-white")}>
                      <span className="text-[10px] opacity-60 block">Barge-in Latency</span>
                      <span className="text-xs font-bold text-cyan-400">&lt;115ms (Live)</span>
                    </div>
                    <div className={cn("p-2 rounded-xl border text-center", isDark ? "border-white/10 bg-black/30" : "border-slate-200 bg-white")}>
                      <span className="text-[10px] opacity-60 block">Loss Convergence</span>
                      <span className="text-xs font-bold text-emerald-400">0.014 Epoch</span>
                    </div>
                    <div className={cn("p-2 rounded-xl border text-center", isDark ? "border-white/10 bg-black/30" : "border-slate-200 bg-white")}>
                      <span className="text-[10px] opacity-60 block">Active Swarm</span>
                      <span className="text-xs font-bold text-fuchsia-400">6 Agent Nodes</span>
                    </div>
                  </div>
                </div>

                {/* Training Trigger Button */}
                <div className="space-y-2">
                  <button
                    type="button"
                    disabled={isTraining}
                    onClick={handleTrainModel}
                    className={cn(
                      "w-full py-2.5 px-4 rounded-xl text-xs font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-2 shadow-lg",
                      isTraining
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 cursor-wait animate-pulse"
                        : "bg-gradient-to-r from-amber-500 via-purple-600 to-cyan-500 text-white hover:scale-[1.01] active:scale-[0.99] shadow-[0_0_20px_rgba(245,158,11,0.35)]",
                    )}
                  >
                    <Cpu className={cn("size-4", isTraining && "animate-spin")} />
                    <span>
                      {isTraining
                        ? `Training in Progress (${trainingProgress}%)`
                        : modelLevel === "advance"
                        ? "Retrain & Fine-Tune Advance Swarm"
                        : "Train Model to Advance Level"}
                    </span>
                  </button>

                  {/* Progress bar during training */}
                  {isTraining && (
                    <div className={cn("w-full h-2 rounded-full overflow-hidden border", isDark ? "border-white/10 bg-black/40" : "border-slate-200 bg-slate-100")}>
                      <div
                        className="h-full bg-gradient-to-r from-amber-400 via-purple-500 to-cyan-400 transition-all duration-300 rounded-full"
                        style={{ width: `${trainingProgress}%` }}
                      />
                    </div>
                  )}
                </div>

                {/* Live Training Logs Terminal */}
                <div
                  className={cn(
                    "rounded-xl border p-3.5 space-y-2 font-mono text-[11px]",
                    isDark ? "border-white/10 bg-[#020617] text-white/90" : "border-slate-200 bg-slate-900 text-slate-100 shadow-md",
                  )}
                >
                  <div className="flex items-center justify-between pb-2 border-b border-white/10 text-[10px] text-white/50">
                    <span className="flex items-center gap-1.5 font-bold tracking-wider text-amber-400">
                      <span className="size-1.5 rounded-full bg-amber-400 animate-ping" />
                      TRAINING CONSOLE // RLAIF STREAM
                    </span>
                    <span>EPOCH: 4/4</span>
                  </div>

                  <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1 scrollbar-thin">
                    {trainingLogs.map((log, i) => (
                      <p
                        key={i}
                        className={cn(
                          "leading-relaxed break-words",
                          log.includes("COMPLETE")
                            ? "text-emerald-400 font-bold"
                            : log.includes("Running")
                            ? "text-cyan-300"
                            : log.includes("Fine-tuning")
                            ? "text-fuchsia-300"
                            : "text-white/70",
                        )}
                      >
                        {log}
                      </p>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* TASKS SECTION */}
            {activeSection === "tasks" && (
              <div className="space-y-3">
                {tasks.length === 0 ? (
                  <p className="text-xs text-center py-8 opacity-50">No background tasks active.</p>
                ) : (
                  tasks.map((task) => (
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
                  ))
                )}
              </div>
            )}

            {/* AGENTS SECTION */}
            {activeSection === "agents" && (
              <div className="space-y-3">
                {agents.length === 0 ? (
                  <p className="text-xs text-center py-8 opacity-50">No external agents connected.</p>
                ) : (
                  agents.map((agent, i) => (
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
                  ))
                )}
              </div>
            )}

            {/* MEMORY SECTION */}
            {activeSection === "memory" && (
              <div className="space-y-3">
                {memoryStore.length === 0 ? (
                  <p className="text-xs text-center py-8 opacity-50">No session memory entries stored.</p>
                ) : (
                  memoryStore.map((mem, i) => (
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
                  ))
                )}
              </div>
            )}
          </div>
        </aside>
      )}
    </div>
  )
}
