"use client"

import React, { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"

export interface ScreenEdgeIlluminationProps {
  active: boolean
  audioLevel?: number // 0 to 1
  state?: "idle" | "listening" | "thinking" | "speaking"
  className?: string
}

const ACCENT_SWATCHES: Record<string, string> = {
  violet: "#7064e8",
  blue: "#3979df",
  teal: "#148b7e",
  rose: "#ce5478",
  amber: "#c86d1a",
}

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  alpha: number
  maxAlpha: number
  fadeSpeed: number
  type: "star" | "mote" | "orb"
  side: "left" | "right" | "top" | "bottom" | "corner"
  cornerIndex: number
  wavePhase: number
  waveSpeed: number
}

// Convert Hex or CSS color to RGB components
function parseRgb(color: string): { r: number; g: number; b: number } {
  if (color.startsWith("#")) {
    const hex = color.replace("#", "")
    if (hex.length === 3) {
      return {
        r: parseInt(hex[0] + hex[0], 16),
        g: parseInt(hex[1] + hex[1], 16),
        b: parseInt(hex[2] + hex[2], 16),
      }
    }
    if (hex.length >= 6) {
      return {
        r: parseInt(hex.substring(0, 2), 16),
        g: parseInt(hex.substring(2, 4), 16),
        b: parseInt(hex.substring(4, 6), 16),
      }
    }
  }
  return { r: 112, g: 100, b: 232 } // default violet #7064e8
}

export function ScreenEdgeIllumination({
  active,
  audioLevel = 0,
  state = "listening",
  className,
}: ScreenEdgeIlluminationProps) {
  const [accentColor, setAccentColor] = useState<string>(() => {
    if (typeof window === "undefined") return "#7064e8"
    const saved = localStorage.getItem("chai-accent")
    return (saved && ACCENT_SWATCHES[saved]) || "#7064e8"
  })

  // Smooth visibility transition for graceful exit dispersal
  const [shouldRender, setShouldRender] = useState(active)
  const [fadeAlpha, setFadeAlpha] = useState(active ? 1 : 0)

  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const animFrameRef = useRef<number | null>(null)
  const particlesRef = useRef<Particle[]>([])
  const activeRef = useRef(active)
  activeRef.current = active

  const stateRef = useRef(state)
  stateRef.current = state

  const isExitingRef = useRef(false)

  const audioLevelRef = useRef(audioLevel)
  audioLevelRef.current = audioLevel

  const accentColorRef = useRef(accentColor)
  accentColorRef.current = accentColor

  // Synchronize accent color with profile settings
  useEffect(() => {
    if (typeof window === "undefined") return

    const updateColor = () => {
      const rootStyle = getComputedStyle(document.documentElement)
      const cssColor = rootStyle.getPropertyValue("--profile-accent-color").trim()
      const savedHex = localStorage.getItem("chai-accent-color")
      const savedChoice = localStorage.getItem("chai-accent")
      const color =
        cssColor ||
        savedHex ||
        (savedChoice && ACCENT_SWATCHES[savedChoice]) ||
        "#7064e8"
      setAccentColor(color)
    }

    updateColor()

    const handleAccentChange = (e: Event) => {
      const custom = e as CustomEvent<string>
      if (custom.detail) {
        if (ACCENT_SWATCHES[custom.detail]) {
          setAccentColor(ACCENT_SWATCHES[custom.detail])
        } else if (custom.detail.startsWith("#") || custom.detail.startsWith("rgb")) {
          setAccentColor(custom.detail)
        } else {
          updateColor()
        }
      } else {
        updateColor()
      }
    }

    const handleStorage = (e: StorageEvent) => {
      if (e.key === "chai-accent" || e.key === "chai-accent-color") {
        updateColor()
      }
    }

    window.addEventListener("chai-accent-change", handleAccentChange as EventListener)
    window.addEventListener("storage", handleStorage)
    return () => {
      window.removeEventListener("chai-accent-change", handleAccentChange as EventListener)
      window.removeEventListener("storage", handleStorage)
    }
  }, [])

  // Smooth entry and graceful exit dissipation at the end
  useEffect(() => {
    if (active) {
      isExitingRef.current = false
      setShouldRender(true)
      const t = setTimeout(() => setFadeAlpha(1), 20)
      return () => clearTimeout(t)
    } else {
      isExitingRef.current = true
      setFadeAlpha(0)
      // Dissolution period: particles disperse outward into darkness before unmounting
      const t = setTimeout(() => {
        setShouldRender(false)
        isExitingRef.current = false
      }, 950)
      return () => clearTimeout(t)
    }
  }, [active])

  // Canvas particle engine along screen edges, corners & exit dissolution
  useEffect(() => {
    if (!shouldRender) return

    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const resizeCanvas = () => {
      canvas.width = window.innerWidth * dpr
      canvas.height = window.innerHeight * dpr
    }
    resizeCanvas()
    window.addEventListener("resize", resizeCanvas)

    const W = window.innerWidth
    const H = window.innerHeight
    const particleCount = 110 // Rich density along screen sides and corners

    // Helper to spawn a particle along the screen edges or corners
    function createParticle(initialSpawn = false): Particle {
      const roll = Math.random()
      let side: "left" | "right" | "top" | "bottom" | "corner" = "left"
      let isCorner = false
      let cornerIndex = 0

      // 35% Left side, 35% Right side, 20% Corners, 10% Top/Bottom
      if (roll < 0.35) {
        side = "left"
      } else if (roll < 0.70) {
        side = "right"
      } else if (roll < 0.90) {
        side = "corner"
        isCorner = true
        cornerIndex = Math.floor(Math.random() * 4)
      } else {
        side = Math.random() < 0.5 ? "top" : "bottom"
      }

      const pTypeRoll = Math.random()
      const type: "star" | "mote" | "orb" =
        pTypeRoll < 0.45 ? "star" : pTypeRoll < 0.82 ? "mote" : "orb"

      let x = 0
      let y = 0
      let vx = 0
      let vy = 0

      if (side === "left") {
        // Floating along the left side band (0px to 80px from left)
        x = Math.random() * 70 + 6
        y = Math.random() * H
        vx = (Math.random() - 0.5) * 0.35
        vy = (Math.random() - 0.5) * 0.9 - 0.2 // subtle upward/downward drift
      } else if (side === "right") {
        // Floating along the right side band (0px to 80px from right)
        x = W - (Math.random() * 70 + 6)
        y = Math.random() * H
        vx = (Math.random() - 0.5) * 0.35
        vy = (Math.random() - 0.5) * 0.9 - 0.2
      } else if (side === "corner") {
        const offset = Math.random() * 130 + 15
        const angle = Math.random() * Math.PI * 0.5
        if (cornerIndex === 0) {
          x = Math.cos(angle) * offset
          y = Math.sin(angle) * offset
          vx = Math.random() * 0.4 + 0.1
          vy = Math.random() * 0.4 + 0.1
        } else if (cornerIndex === 1) {
          x = W - Math.cos(angle) * offset
          y = Math.sin(angle) * offset
          vx = -(Math.random() * 0.4 + 0.1)
          vy = Math.random() * 0.4 + 0.1
        } else if (cornerIndex === 2) {
          x = Math.cos(angle) * offset
          y = H - Math.sin(angle) * offset
          vx = Math.random() * 0.4 + 0.1
          vy = -(Math.random() * 0.4 + 0.1)
        } else {
          x = W - Math.cos(angle) * offset
          y = H - Math.sin(angle) * offset
          vx = -(Math.random() * 0.4 + 0.1)
          vy = -(Math.random() * 0.4 + 0.1)
        }
      } else if (side === "top") {
        x = Math.random() * W
        y = Math.random() * 45 + 5
        vx = (Math.random() - 0.5) * 0.7
        vy = (Math.random() - 0.5) * 0.25
      } else {
        x = Math.random() * W
        y = H - (Math.random() * 45 + 5)
        vx = (Math.random() - 0.5) * 0.7
        vy = (Math.random() - 0.5) * 0.25
      }

      const size =
        type === "star"
          ? Math.random() * 1.5 + 1.2
          : type === "mote"
          ? Math.random() * 2.2 + 2.4
          : Math.random() * 3.5 + 4.5

      const maxAlpha =
        type === "star"
          ? Math.random() * 0.4 + 0.55
          : type === "mote"
          ? Math.random() * 0.35 + 0.45
          : Math.random() * 0.3 + 0.3

      return {
        x,
        y,
        vx,
        vy,
        size,
        alpha: initialSpawn ? Math.random() * maxAlpha : 0,
        maxAlpha,
        fadeSpeed: Math.random() * 0.018 + 0.009,
        type,
        side,
        cornerIndex,
        wavePhase: Math.random() * Math.PI * 2,
        waveSpeed: Math.random() * 0.035 + 0.015,
      }
    }

    particlesRef.current = Array.from({ length: particleCount }, () => createParticle(true))

    let globalAlphaMult = 0
    let frameTime = 0

    const render = () => {
      frameTime += 1
      ctx.save()
      ctx.scale(dpr, dpr)
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)

      const isExiting = isExitingRef.current
      const targetAlpha = activeRef.current ? 1 : 0

      if (isExiting) {
        globalAlphaMult = Math.max(0, globalAlphaMult - 0.024)
      } else {
        globalAlphaMult += (targetAlpha - globalAlphaMult) * 0.08
      }

      const curAudio = audioLevelRef.current
      const curState = stateRef.current
      const colorHex = accentColorRef.current
      const rgb = parseRgb(colorHex)

      // Dynamic speech pulse when the assistant is speaking!
      let dynamicIntensity = 0
      if (curState === "speaking") {
        // Synthetic audio wave during AI speech time
        dynamicIntensity =
          0.35 +
          0.3 * Math.sin(frameTime * 0.09) +
          0.2 * Math.cos(frameTime * 0.17)
      } else if (curState === "listening") {
        // Direct microphone input level
        dynamicIntensity = Math.min(curAudio * 1.2, 1.0)
      } else {
        dynamicIntensity = 0.15
      }

      const speedMultiplier = 1 + dynamicIntensity * 0.75

      const particles = particlesRef.current

      // -------------------------------------------------------------
      // PASS 1: DRAW CONSTELLATION FILAMENTS (AI MATRIX WEB ALONG SIDES)
      // -------------------------------------------------------------
      if (globalAlphaMult > 0.1) {
        const maxDist = 80
        const maxDistSq = maxDist * maxDist

        ctx.lineWidth = 0.9
        for (let i = 0; i < particles.length; i++) {
          const p1 = particles[i]
          if (p1.alpha < 0.2) continue

          for (let j = i + 1; j < particles.length; j++) {
            const p2 = particles[j]
            if (p2.alpha < 0.2) continue

            // Connect if same side or corner
            if (p1.side !== p2.side && !p1.side.includes("corner") && !p2.side.includes("corner")) {
              continue
            }

            const dx = p1.x - p2.x
            const dy = p1.y - p2.y
            const distSq = dx * dx + dy * dy

            if (distSq < maxDistSq) {
              const dist = Math.sqrt(distSq)
              const proximityAlpha =
                (1 - dist / maxDist) * 0.22 * globalAlphaMult * Math.min(p1.alpha, p2.alpha)
              ctx.strokeStyle = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${proximityAlpha})`
              ctx.beginPath()
              ctx.moveTo(p1.x, p1.y)
              ctx.lineTo(p2.x, p2.y)
              ctx.stroke()
            }
          }
        }
      }

      // -------------------------------------------------------------
      // PASS 2: DRAW PARTICLES (STARS, GLOWING MOTES, NEBULA ORBS)
      // -------------------------------------------------------------
      particles.forEach((p, idx) => {
        p.wavePhase += p.waveSpeed

        if (isExiting) {
          // Dissolution effect at the end: particles accelerate outward / disperse
          p.vx *= 1.03
          p.vy *= 1.03
          p.alpha -= 0.022
        } else {
          // Normal harmonic breathing
          p.alpha += p.fadeSpeed
          if (p.alpha >= p.maxAlpha) {
            p.fadeSpeed = -Math.abs(p.fadeSpeed)
          }

          // Respawn if faded out
          if (p.alpha <= 0 && p.fadeSpeed < 0) {
            particles[idx] = createParticle(false)
            return
          }
        }

        // Apply velocities with dynamic speech / voice speed boost
        p.x += p.vx * speedMultiplier
        p.y += p.vy * speedMultiplier

        // Gentle sinusoidal wave across screen side boundaries
        if (p.side === "left" || p.side === "right") {
          p.x += Math.sin(p.wavePhase) * 0.35
        } else if (p.side === "top" || p.side === "bottom") {
          p.y += Math.sin(p.wavePhase) * 0.35
        }

        const effectiveAlpha = Math.max(0, p.alpha * globalAlphaMult)
        if (effectiveAlpha <= 0.005) return

        if (p.type === "orb") {
          // Soft Ethereal Glowing Orb with wide aura
          const haloRadius = p.size * (2.8 + dynamicIntensity * 1.4)
          const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, haloRadius)
          grad.addColorStop(0, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${effectiveAlpha * 0.95})`)
          grad.addColorStop(0.35, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${effectiveAlpha * 0.45})`)
          grad.addColorStop(1, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0)`)

          ctx.beginPath()
          ctx.arc(p.x, p.y, haloRadius, 0, Math.PI * 2)
          ctx.fillStyle = grad
          ctx.fill()
        } else if (p.type === "star") {
          // Brilliant Stardust Spark with white core & accent bloom
          const twinkle = Math.sin(frameTime * 0.12 + p.wavePhase) * 0.3 + 0.7
          const starAlpha = effectiveAlpha * twinkle

          ctx.beginPath()
          ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(255, 255, 255, ${starAlpha * 0.95})`
          ctx.shadowColor = colorHex
          ctx.shadowBlur = 10 + dynamicIntensity * 8
          ctx.fill()
          ctx.shadowBlur = 0
        } else {
          // Luminous Ember Mote
          const moteHalo = p.size * 2.4
          const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, moteHalo)
          grad.addColorStop(0, `rgba(255, 255, 255, ${effectiveAlpha * 0.85})`)
          grad.addColorStop(0.3, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${effectiveAlpha * 0.9})`)
          grad.addColorStop(1, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0)`)

          ctx.beginPath()
          ctx.arc(p.x, p.y, moteHalo, 0, Math.PI * 2)
          ctx.fillStyle = grad
          ctx.fill()
        }
      })

      ctx.restore()

      animFrameRef.current = requestAnimationFrame(render)
    }

    animFrameRef.current = requestAnimationFrame(render)

    return () => {
      window.removeEventListener("resize", resizeCanvas)
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    }
  }, [shouldRender])

  if (!shouldRender) return null

  const rgb = parseRgb(accentColor)
  // Subtle speech pulse for edge lighting during listening or speech time
  const dynamicFactor =
    state === "speaking" ? 0.35 : Math.min(audioLevel * 0.3, 0.3)
  const dynamicBrightness = 1 + dynamicFactor
  const dynamicScale = 1 + dynamicFactor * 0.4

  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none fixed inset-0 z-[80] overflow-hidden select-none transition-opacity duration-700 ease-out",
        className,
      )}
      style={{
        opacity: fadeAlpha,
        filter: `brightness(${dynamicBrightness})`,
      }}
    >
      {/* ------------------------------------------------------------- */}
      {/* 1. VIBRANT SUBTLE SIDES LIGHT (LEFT & RIGHT EDGE ILLUMINATION) */}
      {/* ------------------------------------------------------------- */}
      {/* LEFT SIDE AMBIENT LIGHT BAND */}
      <div
        className="absolute inset-y-0 left-0 w-16 sm:w-24 transition-all duration-300 pointer-events-none"
        style={{
          background: `linear-gradient(90deg, rgba(${rgb.r},${rgb.g},${rgb.b},0.38) 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.16) 45%, rgba(${rgb.r},${rgb.g},${rgb.b},0.03) 80%, transparent 100%)`,
        }}
      />
      {/* LEFT SIDE CRISP NEON SPINE */}
      <div
        className="absolute inset-y-0 left-0 w-[2.5px] transition-all duration-300"
        style={{
          background: `linear-gradient(180deg, transparent 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.95) 15%, rgba(${rgb.r},${rgb.g},${rgb.b},0.95) 85%, transparent 100%)`,
          boxShadow: `0 0 16px 2px rgba(${rgb.r},${rgb.g},${rgb.b},0.65)`,
          opacity: 0.85,
        }}
      />

      {/* RIGHT SIDE AMBIENT LIGHT BAND */}
      <div
        className="absolute inset-y-0 right-0 w-16 sm:w-24 transition-all duration-300 pointer-events-none"
        style={{
          background: `linear-gradient(270deg, rgba(${rgb.r},${rgb.g},${rgb.b},0.38) 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.16) 45%, rgba(${rgb.r},${rgb.g},${rgb.b},0.03) 80%, transparent 100%)`,
        }}
      />
      {/* RIGHT SIDE CRISP NEON SPINE */}
      <div
        className="absolute inset-y-0 right-0 w-[2.5px] transition-all duration-300"
        style={{
          background: `linear-gradient(180deg, transparent 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.95) 15%, rgba(${rgb.r},${rgb.g},${rgb.b},0.95) 85%, transparent 100%)`,
          boxShadow: `0 0 16px 2px rgba(${rgb.r},${rgb.g},${rgb.b},0.65)`,
          opacity: 0.85,
        }}
      />

      {/* ------------------------------------------------------------- */}
      {/* 2. TOP & BOTTOM EDGE ILLUMINATION                              */}
      {/* ------------------------------------------------------------- */}
      {/* TOP EDGE AMBIENT LIGHT */}
      <div
        className="absolute inset-x-0 top-0 h-12 sm:h-16 transition-all duration-300 pointer-events-none"
        style={{
          background: `linear-gradient(180deg, rgba(${rgb.r},${rgb.g},${rgb.b},0.32) 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.12) 45%, transparent 100%)`,
        }}
      />
      {/* TOP EDGE CRISP NEON SPINE */}
      <div
        className="absolute inset-x-0 top-0 h-[2.5px] transition-all duration-300"
        style={{
          background: `linear-gradient(90deg, transparent 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.95) 15%, rgba(${rgb.r},${rgb.g},${rgb.b},0.95) 85%, transparent 100%)`,
          boxShadow: `0 0 16px 2px rgba(${rgb.r},${rgb.g},${rgb.b},0.65)`,
          opacity: 0.85,
        }}
      />

      {/* BOTTOM EDGE AMBIENT LIGHT */}
      <div
        className="absolute inset-x-0 bottom-0 h-12 sm:h-16 transition-all duration-300 pointer-events-none"
        style={{
          background: `linear-gradient(0deg, rgba(${rgb.r},${rgb.g},${rgb.b},0.32) 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.12) 45%, transparent 100%)`,
        }}
      />
      {/* BOTTOM EDGE CRISP NEON SPINE */}
      <div
        className="absolute inset-x-0 bottom-0 h-[2.5px] transition-all duration-300"
        style={{
          background: `linear-gradient(90deg, transparent 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.95) 15%, rgba(${rgb.r},${rgb.g},${rgb.b},0.95) 85%, transparent 100%)`,
          boxShadow: `0 0 16px 2px rgba(${rgb.r},${rgb.g},${rgb.b},0.65)`,
          opacity: 0.85,
        }}
      />

      {/* ------------------------------------------------------------- */}
      {/* 3. FOUR CORNER AMBIENT NEBULAS & HUD BRACKETS                  */}
      {/* ------------------------------------------------------------- */}
      {/* Top-Left Corner Ambient Nebula */}
      <div
        className="absolute -top-24 -left-24 size-80 sm:size-96 rounded-full blur-[85px] transition-transform duration-300 pointer-events-none"
        style={{
          background: `radial-gradient(circle, rgba(${rgb.r},${rgb.g},${rgb.b},0.3) 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.1) 50%, transparent 75%)`,
          transform: `scale(${dynamicScale})`,
        }}
      />
      {/* Top-Right Corner Ambient Nebula */}
      <div
        className="absolute -top-24 -right-24 size-80 sm:size-96 rounded-full blur-[85px] transition-transform duration-300 pointer-events-none"
        style={{
          background: `radial-gradient(circle, rgba(${rgb.r},${rgb.g},${rgb.b},0.3) 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.1) 50%, transparent 75%)`,
          transform: `scale(${dynamicScale})`,
        }}
      />
      {/* Bottom-Left Corner Ambient Nebula */}
      <div
        className="absolute -bottom-24 -left-24 size-80 sm:size-96 rounded-full blur-[85px] transition-transform duration-300 pointer-events-none"
        style={{
          background: `radial-gradient(circle, rgba(${rgb.r},${rgb.g},${rgb.b},0.3) 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.1) 50%, transparent 75%)`,
          transform: `scale(${dynamicScale})`,
        }}
      />
      {/* Bottom-Right Corner Ambient Nebula */}
      <div
        className="absolute -bottom-24 -right-24 size-80 sm:size-96 rounded-full blur-[85px] transition-transform duration-300 pointer-events-none"
        style={{
          background: `radial-gradient(circle, rgba(${rgb.r},${rgb.g},${rgb.b},0.3) 0%, rgba(${rgb.r},${rgb.g},${rgb.b},0.1) 50%, transparent 75%)`,
          transform: `scale(${dynamicScale})`,
        }}
      />

      {/* REFINED CORNER HUD ACCENTS */}
      {/* Top-Left Bracket */}
      <svg
        className="absolute top-3 left-3 size-8 sm:size-10 transition-opacity duration-300"
        style={{ color: accentColor, opacity: 0.85, filter: "drop-shadow(0 0 6px currentColor)" }}
        viewBox="0 0 40 40"
        fill="none"
      >
        <path
          d="M3 24 V10 C3 6.13 6.13 3 10 3 H24"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="3" cy="3" r="2.2" fill="currentColor" />
      </svg>
      {/* Top-Right Bracket */}
      <svg
        className="absolute top-3 right-3 size-8 sm:size-10 transition-opacity duration-300"
        style={{ color: accentColor, opacity: 0.85, filter: "drop-shadow(0 0 6px currentColor)" }}
        viewBox="0 0 40 40"
        fill="none"
      >
        <path
          d="M37 24 V10 C37 6.13 33.87 3 30 3 H16"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="37" cy="3" r="2.2" fill="currentColor" />
      </svg>
      {/* Bottom-Left Bracket */}
      <svg
        className="absolute bottom-3 left-3 size-8 sm:size-10 transition-opacity duration-300"
        style={{ color: accentColor, opacity: 0.85, filter: "drop-shadow(0 0 6px currentColor)" }}
        viewBox="0 0 40 40"
        fill="none"
      >
        <path
          d="M3 16 V30 C3 33.87 6.13 37 10 37 H24"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="3" cy="37" r="2.2" fill="currentColor" />
      </svg>
      {/* Bottom-Right Bracket */}
      <svg
        className="absolute bottom-3 right-3 size-8 sm:size-10 transition-opacity duration-300"
        style={{ color: accentColor, opacity: 0.85, filter: "drop-shadow(0 0 6px currentColor)" }}
        viewBox="0 0 40 40"
        fill="none"
      >
        <path
          d="M37 16 V30 C37 33.87 33.87 37 30 37 H16"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="37" cy="37" r="2.2" fill="currentColor" />
      </svg>

      {/* ------------------------------------------------------------- */}
      {/* 4. IMMERSIVE EDGE & CORNER PARTICLE CANVAS (110 PARTICLES)     */}
      {/* ------------------------------------------------------------- */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none block size-full"
      />

      {/* ------------------------------------------------------------- */}
      {/* 5. GENTLE SOFT VIGNETTE FEATHERING (MILD ACCENT HALO)          */}
      {/* ------------------------------------------------------------- */}
      <div
        className="absolute inset-0 transition-opacity duration-500"
        style={{
          boxShadow: `inset 0 0 46px 2px rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.12)`,
        }}
      />
    </div>
  )
}
