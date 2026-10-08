'use client'

import { useEffect, useRef } from 'react'

type ParticleTheme = 'dark' | 'light'

type Particle = {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  opacity: number
  phase: number
}

export function ParticleField({ theme }: { theme: ParticleTheme }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const context = canvas.getContext('2d', { alpha: true })
    if (!context) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    let width = 0
    let height = 0
    let frame = 0
    let particles: Particle[] = []

    function resize() {
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
      width = window.innerWidth
      height = window.innerHeight
      canvas!.width = Math.round(width * pixelRatio)
      canvas!.height = Math.round(height * pixelRatio)
      context!.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)

      const count = Math.max(42, Math.min(112, Math.round((width * height) / 13500)))
      particles = Array.from({ length: count }, () => {
        const angle = Math.random() * Math.PI * 2
        const speed = 0.035 + Math.random() * 0.11

        return {
          x: Math.random() * width,
          y: Math.random() * height,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          radius: 0.55 + Math.random() * 1.15,
          opacity: 0.1 + Math.random() * 0.2,
          phase: Math.random() * Math.PI * 2,
        }
      })
    }

    function draw(time = 0) {
      context?.clearRect(0, 0, width, height)
      if (!context) return

      const color = theme === 'dark' ? '226, 226, 226' : '70, 70, 70'
      const motionIsAllowed = !reducedMotion.matches

      for (const particle of particles) {
        const twinkle = 0.8 + Math.sin(time / 1600 + particle.phase) * 0.2
        context.beginPath()
        context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2)
        context.fillStyle = `rgba(${color}, ${particle.opacity * twinkle})`
        context.fill()

        if (motionIsAllowed) {
          particle.x += particle.vx
          particle.y += particle.vy
          if (particle.x < -2) particle.x = width + 2
          if (particle.x > width + 2) particle.x = -2
          if (particle.y < -2) particle.y = height + 2
          if (particle.y > height + 2) particle.y = -2
        }
      }

      if (motionIsAllowed) frame = window.requestAnimationFrame(draw)
    }

    function restart() {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(draw)
    }

    resize()
    restart()
    window.addEventListener('resize', resize)
    window.addEventListener('resize', restart)
    reducedMotion.addEventListener('change', restart)

    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', resize)
      window.removeEventListener('resize', restart)
      reducedMotion.removeEventListener('change', restart)
    }
  }, [theme])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 size-full"
    />
  )
}
