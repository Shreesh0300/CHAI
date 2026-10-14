"use client"

import { useState, useEffect } from "react"
import { getLogoPalette, updateBrowserFavicon, type LogoPalette } from "@/lib/brand-palette"

export function useChaiTheme() {
  const [isDark, setIsDark] = useState<boolean>(() => {
    if (typeof window === "undefined") return true
    return localStorage.getItem("chai-theme") !== "light"
  })

  const [accent, setAccent] = useState<string>(() => {
    if (typeof window === "undefined") return "violet"
    return localStorage.getItem("chai-accent") || "violet"
  })

  const palette: LogoPalette = getLogoPalette(accent, isDark)

  useEffect(() => {
    // Sync browser tab favicon whenever palette changes
    updateBrowserFavicon(palette)
  }, [palette])

  useEffect(() => {
    const handleThemeChange = (e: Event) => {
      const custom = e as CustomEvent<string>
      if (custom.detail) {
        setIsDark(custom.detail !== "light")
      }
    }

    const handleAccentChange = (e: Event) => {
      const custom = e as CustomEvent<string>
      if (custom.detail) {
        setAccent(custom.detail)
      }
    }

    window.addEventListener("chai-theme-change", handleThemeChange as EventListener)
    window.addEventListener("chai-accent-change", handleAccentChange as EventListener)

    return () => {
      window.removeEventListener("chai-theme-change", handleThemeChange as EventListener)
      window.removeEventListener("chai-accent-change", handleAccentChange as EventListener)
    }
  }, [])

  return { isDark, accent, palette }
}
