"use client"

import React, { useEffect, useRef } from "react"
import { cn } from "@/lib/utils"

export type AssistantVoiceState = "idle" | "listening" | "thinking" | "speaking"

export interface AssistantOrbProps {
  state?: AssistantVoiceState
  audioLevel?: number // 0 to 1
  audioAnalyser?: AnalyserNode | null
  size?: number
  theme?: "dark" | "light" | "auto"
  className?: string
  onClick?: () => void
  interactive?: boolean
}

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  alpha: number
  hue: number
  baseAlpha: number
}

interface OrbitParticle {
  angle: number
  speed: number
  radius: number
  size: number
  color: string
}

export function AssistantOrb({
  state = "idle",
  audioLevel = 0,
  audioAnalyser = null,
  size = 360,
  theme = "auto",
  className,
  onClick,
  interactive = true,
}: AssistantOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const animFrameRef = useRef<number | null>(null)

  // Mutable animation state references
  const stateRef = useRef(state)
  stateRef.current = state

  const audioLevelRef = useRef(audioLevel)
  audioLevelRef.current = audioLevel

  const analyserRef = useRef(audioAnalyser)
  analyserRef.current = audioAnalyser

  const themeRef = useRef(theme)
  themeRef.current = theme

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    // High DPI scaling
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = size * dpr
    canvas.height = size * dpr

    // Internal particles
    const particleCount = 28
    const particles: Particle[] = Array.from({ length: particleCount }, () => ({
      x: (Math.random() - 0.5) * (size * 0.75),
      y: (Math.random() - 0.5) * (size * 0.75),
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      size: Math.random() * 2 + 1,
      alpha: Math.random() * 0.6 + 0.2,
      baseAlpha: Math.random() * 0.6 + 0.2,
      hue: Math.random() > 0.5 ? 185 : 320, // Cyan or Magenta/Pink
    }))

    // Orbiting particles (for thinking/processing state)
    const orbitCount = 8
    const orbitParticles: OrbitParticle[] = Array.from({ length: orbitCount }, (_, i) => ({
      angle: (i / orbitCount) * Math.PI * 2,
      speed: 0.02 + Math.random() * 0.02,
      radius: size * 0.46 + (Math.random() - 0.5) * 16,
      size: Math.random() * 2.5 + 1.5,
      color: i % 2 === 0 ? "#00f5ff" : "#ff2d87",
    }))

    let rotationAngle = 0
    let counterRotation = 0
    let pulsePhase = 0
    let startTime = performance.now()
    const freqData = new Uint8Array(64)

    const numBars = 42
    const prevBarHeights = new Float32Array(numBars).fill(4)

    function render(currentTime: number) {
      if (!ctx || !canvas) return
      const elapsed = (currentTime - startTime) / 1000
      const currentState = stateRef.current
      const currentLevel = audioLevelRef.current
      const analyser = analyserRef.current

      // Read audio analyser frequency data if available
      if (analyser) {
        try {
          analyser.getByteFrequencyData(freqData)
        } catch {
          // ignore context errors
        }
      }

      ctx.save()
      ctx.scale(dpr, dpr)
      ctx.clearRect(0, 0, size, size)

      const cx = size / 2
      const cy = size / 2
      const baseRadius = size * 0.38

      // Speed multipliers based on state
      let speedMult = 1
      let rotationSpeed = 0.006
      let glowColor = "rgba(0, 245, 255, 0.45)"
      let bloomSpread = 24
      let pulseAmplitude = 3

      if (currentState === "idle") {
        speedMult = 0.8
        rotationSpeed = 0.004
        glowColor = "rgba(0, 245, 255, 0.35)"
        bloomSpread = 20
        pulseAmplitude = 3
      } else if (currentState === "listening") {
        speedMult = 1.4
        rotationSpeed = 0.012
        glowColor = "rgba(0, 245, 255, 0.75)"
        bloomSpread = 38
        pulseAmplitude = 5 + currentLevel * 8
      } else if (currentState === "thinking") {
        speedMult = 2.2
        rotationSpeed = 0.028
        glowColor = "rgba(168, 85, 247, 0.65)"
        bloomSpread = 32
        pulseAmplitude = 4
      } else if (currentState === "speaking") {
        speedMult = 1.8
        rotationSpeed = 0.014
        glowColor = "rgba(255, 45, 135, 0.75)"
        bloomSpread = 42
        pulseAmplitude = 6 + currentLevel * 10
      }

      pulsePhase += 0.03 * speedMult
      rotationAngle += rotationSpeed
      counterRotation -= rotationSpeed * 0.75

      const pulseScale = 1 + (Math.sin(pulsePhase) * pulseAmplitude) / baseRadius
      const orbRadius = baseRadius * pulseScale

      // -------------------------------------------------------------
      // 1. Ambient Background Glow Behind Orb
      // -------------------------------------------------------------
      const ambientGlow = ctx.createRadialGradient(cx, cy, orbRadius * 0.2, cx, cy, orbRadius * 1.35)
      if (currentState === "speaking") {
        ambientGlow.addColorStop(0, "rgba(255, 45, 135, 0.28)")
        ambientGlow.addColorStop(0.5, "rgba(121, 40, 202, 0.16)")
        ambientGlow.addColorStop(1, "rgba(0, 0, 0, 0)")
      } else if (currentState === "thinking") {
        ambientGlow.addColorStop(0, "rgba(139, 92, 246, 0.26)")
        ambientGlow.addColorStop(0.5, "rgba(59, 130, 246, 0.14)")
        ambientGlow.addColorStop(1, "rgba(0, 0, 0, 0)")
      } else {
        ambientGlow.addColorStop(0, "rgba(0, 245, 255, 0.25)")
        ambientGlow.addColorStop(0.5, "rgba(0, 132, 255, 0.12)")
        ambientGlow.addColorStop(1, "rgba(0, 0, 0, 0)")
      }
      ctx.fillStyle = ambientGlow
      ctx.beginPath()
      ctx.arc(cx, cy, orbRadius * 1.35, 0, Math.PI * 2)
      ctx.fill()

      // -------------------------------------------------------------
      // 2. Outer Rotating Energy Rings (JARVIS style)
      // -------------------------------------------------------------
      ctx.save()
      ctx.translate(cx, cy)

      // Outer Ring 1: Clockwise Dashed Energy Ring
      ctx.rotate(rotationAngle)
      ctx.beginPath()
      ctx.arc(0, 0, orbRadius * 1.15, 0, Math.PI * 2)
      ctx.strokeStyle = currentState === "speaking" ? "rgba(255, 45, 135, 0.35)" : "rgba(0, 245, 255, 0.3)"
      ctx.lineWidth = 1.2
      ctx.setLineDash([14, 28, 4, 28])
      ctx.stroke()
      ctx.restore()

      // Outer Ring 2: Counter-Clockwise Segmented Arc
      ctx.save()
      ctx.translate(cx, cy)
      ctx.rotate(counterRotation)
      ctx.beginPath()
      ctx.arc(0, 0, orbRadius * 1.07, 0, Math.PI * 2)
      ctx.strokeStyle = currentState === "thinking" ? "rgba(168, 85, 247, 0.45)" : "rgba(0, 132, 255, 0.28)"
      ctx.lineWidth = 1
      ctx.setLineDash([40, 15, 8, 15])
      ctx.stroke()
      ctx.restore()

      // -------------------------------------------------------------
      // 3. Orbiting Data Nodes / Processing Particles
      // -------------------------------------------------------------
      orbitParticles.forEach((op) => {
        op.angle += op.speed * speedMult
        const px = cx + Math.cos(op.angle) * op.radius
        const py = cy + Math.sin(op.angle) * op.radius

        ctx.save()
        ctx.beginPath()
        ctx.arc(px, py, op.size, 0, Math.PI * 2)
        ctx.fillStyle = op.color
        ctx.shadowColor = op.color
        ctx.shadowBlur = 8
        ctx.fill()
        ctx.restore()
      })

      // -------------------------------------------------------------
      // 4. Subtle Floating Dust Particles around Orb
      // -------------------------------------------------------------
      particles.forEach((p) => {
        p.x += p.vx * speedMult
        p.y += p.vy * speedMult

        // Wrap particles within bounded area
        const maxDist = orbRadius * 1.2
        const dist = Math.hypot(p.x, p.y)
        if (dist > maxDist) {
          p.x = -p.x * 0.7
          p.y = -p.y * 0.7
        }

        ctx.save()
        ctx.beginPath()
        ctx.arc(cx + p.x, cy + p.y, p.size, 0, Math.PI * 2)
        ctx.fillStyle = p.hue === 185 ? `rgba(0, 245, 255, ${p.alpha})` : `rgba(255, 45, 135, ${p.alpha})`
        ctx.fill()
        ctx.restore()
      })

      // -------------------------------------------------------------
      // 5. Dark Glass Inner Core Background
      // -------------------------------------------------------------
      ctx.save()
      ctx.beginPath()
      ctx.arc(cx, cy, orbRadius, 0, Math.PI * 2)
      ctx.clip()

      const currentTheme = themeRef.current
      const isDark =
        currentTheme === "dark" ||
        (currentTheme === "auto" &&
          (typeof window === "undefined" || window.matchMedia("(prefers-color-scheme: dark)").matches))

      // Core radial gradient
      const coreGradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, orbRadius)
      if (isDark) {
        coreGradient.addColorStop(0, "rgba(12, 16, 28, 0.94)")
        coreGradient.addColorStop(0.7, "rgba(8, 10, 20, 0.96)")
        coreGradient.addColorStop(1, "rgba(4, 5, 12, 0.98)")
      } else {
        coreGradient.addColorStop(0, "rgba(244, 248, 255, 0.96)")
        coreGradient.addColorStop(0.7, "rgba(235, 242, 255, 0.98)")
        coreGradient.addColorStop(1, "rgba(220, 230, 250, 0.99)")
      }
      ctx.fillStyle = coreGradient
      ctx.fillRect(cx - orbRadius, cy - orbRadius, orbRadius * 2, orbRadius * 2)

      // Inner subtle coordinate reticles / concentric guides
      ctx.beginPath()
      ctx.arc(cx, cy, orbRadius * 0.68, 0, Math.PI * 2)
      ctx.strokeStyle = isDark ? "rgba(255, 255, 255, 0.04)" : "rgba(0, 40, 100, 0.06)"
      ctx.lineWidth = 1
      ctx.stroke()

      ctx.beginPath()
      ctx.arc(cx, cy, orbRadius * 0.36, 0, Math.PI * 2)
      ctx.strokeStyle = isDark ? "rgba(0, 245, 255, 0.06)" : "rgba(0, 180, 230, 0.12)"
      ctx.lineWidth = 1
      ctx.stroke()

      // Horizontal subtle datum guide
      ctx.beginPath()
      ctx.moveTo(cx - orbRadius * 0.82, cy)
      ctx.lineTo(cx + orbRadius * 0.82, cy)
      ctx.strokeStyle = isDark ? "rgba(0, 245, 255, 0.08)" : "rgba(0, 180, 230, 0.15)"
      ctx.lineWidth = 1
      ctx.stroke()

      // -------------------------------------------------------------
      // 6. Center Audio Waveform Spectrum Bars (Not a plain EQ)
      // -------------------------------------------------------------
      const totalWidth = orbRadius * 1.55
      const barWidth = 3.2
      const gap = (totalWidth - numBars * barWidth) / (numBars - 1)
      const startX = cx - totalWidth / 2
      const maxHeight = orbRadius * 0.72
      const mid = (numBars - 1) / 2

      for (let i = 0; i < numBars; i++) {
        // Gaussian bell-curve envelope: highest in center, tapering to sides
        const distFromMid = Math.abs(i - mid) / mid
        const envelope = Math.exp(-Math.pow(distFromMid * 1.5, 2))

        let targetH = 6

        if (analyser) {
          // Map to real analyser data
          const bin = Math.min(Math.floor((i / numBars) * freqData.length), freqData.length - 1)
          const val = freqData[bin] / 255
          targetH = (val * maxHeight * 0.9 + 5) * envelope
        } else if (currentState === "idle") {
          // Slow breathing sine wave
          const wave = Math.sin(elapsed * 1.6 + i * 0.28) * 0.5 + 0.5
          targetH = (wave * 20 + 6) * envelope
        } else if (currentState === "listening") {
          // React to microphone level + simulated audio dynamics
          const flutter = Math.sin(elapsed * 6 + i * 0.45) * Math.cos(elapsed * 3 + i * 0.2)
          const audioBoost = currentLevel > 0 ? currentLevel * maxHeight * 1.2 : (Math.abs(flutter) * 35 + 8)
          targetH = Math.max(6, audioBoost * envelope)
        } else if (currentState === "thinking") {
          // Rapid high-frequency tight ripple
          const ripple = Math.sin(elapsed * 9 + i * 0.65) * 0.5 + 0.5
          targetH = (ripple * 16 + 5) * envelope * 0.75
        } else if (currentState === "speaking") {
          // Highly dynamic speech wave
          const voiceWave1 = Math.sin(elapsed * 5.2 + i * 0.35)
          const voiceWave2 = Math.cos(elapsed * 8.4 + i * 0.55)
          const voiceCombined = (voiceWave1 + voiceWave2 + 2) / 4
          const amp = currentLevel > 0 ? currentLevel * maxHeight * 1.3 : maxHeight * 0.8
          targetH = Math.max(8, (voiceCombined * amp + 8) * envelope)
        }

        // Smooth interpolation for fluid 60fps dynamics
        prevBarHeights[i] += (targetH - prevBarHeights[i]) * 0.24
        const barH = prevBarHeights[i]

        const bx = startX + i * (barWidth + gap)
        const by = cy - barH / 2

        // RGB Neon Gradient for bars
        const barGrad = ctx.createLinearGradient(bx, by, bx, by + barH)
        if (currentState === "speaking") {
          barGrad.addColorStop(0, "rgba(255, 45, 135, 0.95)")
          barGrad.addColorStop(0.5, "rgba(255, 255, 255, 0.98)")
          barGrad.addColorStop(1, "rgba(121, 40, 202, 0.9)")
        } else if (currentState === "thinking") {
          barGrad.addColorStop(0, "rgba(168, 85, 247, 0.95)")
          barGrad.addColorStop(0.5, "rgba(255, 255, 255, 0.98)")
          barGrad.addColorStop(1, "rgba(59, 130, 246, 0.9)")
        } else {
          barGrad.addColorStop(0, "rgba(0, 245, 255, 0.95)")
          barGrad.addColorStop(0.5, "rgba(255, 255, 255, 0.98)")
          barGrad.addColorStop(1, "rgba(0, 132, 255, 0.9)")
        }

        ctx.fillStyle = barGrad
        ctx.beginPath()
        // Draw rounded capsule bar
        const radius = barWidth / 2
        ctx.roundRect(bx, by, barWidth, barH, radius)
        ctx.fill()
      }

      // Central core radiant pulse flare
      const flareGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, orbRadius * 0.3)
      if (currentState === "speaking") {
        flareGrad.addColorStop(0, "rgba(255, 45, 135, 0.32)")
        flareGrad.addColorStop(1, "rgba(255, 45, 135, 0)")
      } else if (currentState === "thinking") {
        flareGrad.addColorStop(0, "rgba(168, 85, 247, 0.3)")
        flareGrad.addColorStop(1, "rgba(168, 85, 247, 0)")
      } else {
        flareGrad.addColorStop(0, "rgba(0, 245, 255, 0.28)")
        flareGrad.addColorStop(1, "rgba(0, 245, 255, 0)")
      }
      ctx.fillStyle = flareGrad
      ctx.beginPath()
      ctx.arc(cx, cy, orbRadius * 0.3, 0, Math.PI * 2)
      ctx.fill()

      ctx.restore() // End clip of inner core

      // -------------------------------------------------------------
      // 7. Glowing Outer Boundary Ring with Neon Bloom
      // -------------------------------------------------------------
      ctx.save()
      ctx.beginPath()
      ctx.arc(cx, cy, orbRadius, 0, Math.PI * 2)

      // Ring stroke gradient
      const ringGrad = ctx.createLinearGradient(cx - orbRadius, cy - orbRadius, cx + orbRadius, cy + orbRadius)
      ringGrad.addColorStop(0, "#00f5ff")
      ringGrad.addColorStop(0.25, "#0084ff")
      ringGrad.addColorStop(0.55, "#7928ca")
      ringGrad.addColorStop(0.85, "#d600aa")
      ringGrad.addColorStop(1, "#ff2d87")

      ctx.strokeStyle = ringGrad
      ctx.lineWidth = currentState === "listening" ? 2.5 : 2
      ctx.shadowColor = glowColor
      ctx.shadowBlur = bloomSpread
      ctx.stroke()
      ctx.restore()

      ctx.restore() // End scale(dpr, dpr)

      animFrameRef.current = requestAnimationFrame(render)
    }

    animFrameRef.current = requestAnimationFrame(render)

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    }
  }, [size])

  return (
    <div
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={interactive ? onClick : undefined}
      onKeyDown={(e) => {
        if (interactive && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault()
          onClick?.()
        }
      }}
      aria-label={`AI Assistant Core - State: ${state}`}
      className={cn(
        "relative flex items-center justify-center select-none transition-transform duration-300",
        interactive && "cursor-pointer hover:scale-[1.02] active:scale-[0.98]",
        className,
      )}
      style={{ width: size, height: size }}
    >
      <canvas
        ref={canvasRef}
        style={{ width: size, height: size }}
        className="pointer-events-none block"
      />
    </div>
  )
}
