/**
 * CHAI Dynamic Brand Palette & Logo Color Mapping System
 * 
 * Provides theme-aware palette tokens for the CHAI logo and favicon.
 * Ensures the logo harmonizes with the user's chosen accent color without
 * blending into buttons or backgrounds.
 */

export interface LogoPalette {
  primary: string      // Main face silhouette, circuit branches, wordmark
  secondary: string    // Glasses, circuit terminal nodes, eye reticles
  accent: string       // Lens tint, subtle glow highlights
  tagline: string      // "SINCE 2026" tracking text
  swatch: string       // Theme swatch color for UI settings
  label: string        // Display name
}

export type SupportedAccent =
  | "violet"
  | "purple"
  | "blue"
  | "teal"
  | "cyan"
  | "rose"
  | "pink"
  | "amber"
  | "orange"
  | "green"
  | "red"
  | "yellow"
  | "monochrome"

export interface AccentThemeDef {
  label: string
  swatch: string
  dark: LogoPalette
  light: LogoPalette
}

export const BRAND_PALETTES: Record<string, AccentThemeDef> = {
  violet: {
    label: "Violet (Purple)",
    swatch: "#7064e8",
    dark: {
      primary: "#e0e7ff",
      secondary: "#a78bfa",
      accent: "#c084fc",
      tagline: "#94a3b8",
      swatch: "#7064e8",
      label: "Violet",
    },
    light: {
      primary: "#2e1065", // Deep indigo
      secondary: "#7c3aed", // Lavender / purple
      accent: "#6366f1",
      tagline: "#64748b",
      swatch: "#7064e8",
      label: "Violet",
    },
  },
  purple: {
    label: "Purple",
    swatch: "#8b5cf6",
    dark: {
      primary: "#ede9fe",
      secondary: "#c084fc",
      accent: "#a855f7",
      tagline: "#94a3b8",
      swatch: "#8b5cf6",
      label: "Purple",
    },
    light: {
      primary: "#312e81", // Deep indigo
      secondary: "#9333ea", // Lavender highlight
      accent: "#7e22ce",
      tagline: "#64748b",
      swatch: "#8b5cf6",
      label: "Purple",
    },
  },
  blue: {
    label: "Blue",
    swatch: "#3979df",
    dark: {
      primary: "#e0f2fe",
      secondary: "#38bdf8", // Electric blue
      accent: "#60a5fa",
      tagline: "#94a3b8",
      swatch: "#3979df",
      label: "Blue",
    },
    light: {
      primary: "#0c2340", // Deep navy
      secondary: "#2563eb", // Electric blue
      accent: "#1d4ed8",
      tagline: "#64748b",
      swatch: "#3979df",
      label: "Blue",
    },
  },
  teal: {
    label: "Teal (Cyan)",
    swatch: "#148b7e",
    dark: {
      primary: "#ccfbf1",
      secondary: "#2dd4bf", // Soft cyan
      accent: "#14b8a6",
      tagline: "#94a3b8",
      swatch: "#148b7e",
      label: "Teal",
    },
    light: {
      primary: "#042f2e", // Deep teal
      secondary: "#0d9488", // Soft cyan
      accent: "#0f766e",
      tagline: "#64748b",
      swatch: "#148b7e",
      label: "Teal",
    },
  },
  cyan: {
    label: "Cyan",
    swatch: "#06b6d4",
    dark: {
      primary: "#cffafe",
      secondary: "#22d3ee",
      accent: "#06b6d4",
      tagline: "#94a3b8",
      swatch: "#06b6d4",
      label: "Cyan",
    },
    light: {
      primary: "#164e63", // Deep teal
      secondary: "#0891b2", // Soft cyan
      accent: "#0e7490",
      tagline: "#64748b",
      swatch: "#06b6d4",
      label: "Cyan",
    },
  },
  rose: {
    label: "Rose (Pink)",
    swatch: "#ce5478",
    dark: {
      primary: "#ffe4e6",
      secondary: "#fb7185", // Rose pink
      accent: "#f43f5e",
      tagline: "#94a3b8",
      swatch: "#ce5478",
      label: "Rose",
    },
    light: {
      primary: "#4c0519", // Burgundy
      secondary: "#e11d48", // Rose pink
      accent: "#be123c",
      tagline: "#64748b",
      swatch: "#ce5478",
      label: "Rose",
    },
  },
  pink: {
    label: "Pink",
    swatch: "#ec4899",
    dark: {
      primary: "#fce7f3",
      secondary: "#f472b6",
      accent: "#ec4899",
      tagline: "#94a3b8",
      swatch: "#ec4899",
      label: "Pink",
    },
    light: {
      primary: "#831843", // Burgundy
      secondary: "#db2777", // Rose pink
      accent: "#9d174d",
      tagline: "#64748b",
      swatch: "#ec4899",
      label: "Pink",
    },
  },
  amber: {
    label: "Amber (Orange)",
    swatch: "#c86d1a",
    dark: {
      primary: "#fef3c7",
      secondary: "#fbbf24", // Warm amber
      accent: "#f59e0b",
      tagline: "#94a3b8",
      swatch: "#c86d1a",
      label: "Amber",
    },
    light: {
      primary: "#451a03", // Dark brown
      secondary: "#d97706", // Warm amber
      accent: "#b45309",
      tagline: "#64748b",
      swatch: "#c86d1a",
      label: "Amber",
    },
  },
  orange: {
    label: "Orange",
    swatch: "#f97316",
    dark: {
      primary: "#ffedd5",
      secondary: "#fb923c",
      accent: "#ea580c",
      tagline: "#94a3b8",
      swatch: "#f97316",
      label: "Orange",
    },
    light: {
      primary: "#7c2d12", // Dark brown
      secondary: "#ea580c", // Warm amber/orange
      accent: "#c2410c",
      tagline: "#64748b",
      swatch: "#f97316",
      label: "Orange",
    },
  },
  green: {
    label: "Green",
    swatch: "#10b981",
    dark: {
      primary: "#dcfce7",
      secondary: "#34d399", // Mint
      accent: "#10b981",
      tagline: "#94a3b8",
      swatch: "#10b981",
      label: "Green",
    },
    light: {
      primary: "#052e16", // Deep forest green
      secondary: "#059669", // Mint
      accent: "#047857",
      tagline: "#64748b",
      swatch: "#10b981",
      label: "Green",
    },
  },
  red: {
    label: "Red",
    swatch: "#ef4444",
    dark: {
      primary: "#fee2e2",
      secondary: "#f87171", // Muted crimson
      accent: "#ef4444",
      tagline: "#94a3b8",
      swatch: "#ef4444",
      label: "Red",
    },
    light: {
      primary: "#450a0a", // Deep maroon
      secondary: "#dc2626", // Muted crimson
      accent: "#991b1b",
      tagline: "#64748b",
      swatch: "#ef4444",
      label: "Red",
    },
  },
  yellow: {
    label: "Yellow",
    swatch: "#eab308",
    dark: {
      primary: "#fef9c3",
      secondary: "#facc15", // Muted golden yellow
      accent: "#eab308",
      tagline: "#94a3b8",
      swatch: "#eab308",
      label: "Yellow",
    },
    light: {
      primary: "#362503", // Olive
      secondary: "#ca8a04", // Muted golden yellow
      accent: "#854d0e",
      tagline: "#64748b",
      swatch: "#eab308",
      label: "Yellow",
    },
  },
  monochrome: {
    label: "Monochrome",
    swatch: "#64748b",
    dark: {
      primary: "#f8fafc", // Crisp silver-white
      secondary: "#94a3b8", // Neutral gray
      accent: "#cbd5e1",
      tagline: "#64748b",
      swatch: "#64748b",
      label: "Monochrome",
    },
    light: {
      primary: "#020617", // Charcoal
      secondary: "#475569", // Neutral gray
      accent: "#334155",
      tagline: "#94a3b8",
      swatch: "#64748b",
      label: "Monochrome",
    },
  },
}

/**
 * Resolves the logo palette for a given accent key and theme mode.
 * Safe fallback to "violet".
 */
export function getLogoPalette(accentKey?: string | null, isDark: boolean = true): LogoPalette {
  const normalized = (accentKey || "violet").toLowerCase().trim()
  const themeDef = BRAND_PALETTES[normalized] || BRAND_PALETTES.violet
  return isDark ? themeDef.dark : themeDef.light
}

/**
 * Generates standalone SVG code for the CHAI Favicon (AI face wearing glasses + circuit branches).
 * Designed for maximum clarity and contrast at 16x16, 32x32, and 48x48.
 */
export function getChaiFaviconSvg(palette: LogoPalette): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">
  <!-- Circuit tree crown -->
  <path d="M32 20V8M32 17L22 11V6M32 17L42 11V6M22 11L15 15M42 11L49 15" stroke="${palette.secondary}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="32" cy="6" r="2.5" fill="${palette.secondary}"/>
  <circle cx="22" cy="4.5" r="2" fill="${palette.secondary}"/>
  <circle cx="42" cy="4.5" r="2" fill="${palette.secondary}"/>
  <circle cx="13" cy="16" r="2" fill="${palette.secondary}"/>
  <circle cx="51" cy="16" r="2" fill="${palette.secondary}"/>

  <!-- Stylized AI Face Outline -->
  <path d="M19 24C14 28 14 41 16 47C18 53 24 58 32 61C40 58 46 53 48 47C50 41 50 28 45 24C39 20 25 20 19 24Z" stroke="${palette.primary}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>

  <!-- High-Tech Glasses -->
  <rect x="18" y="31" width="11" height="9" rx="2.5" stroke="${palette.secondary}" stroke-width="2.5" fill="${palette.secondary}" fill-opacity="0.2"/>
  <rect x="35" y="31" width="11" height="9" rx="2.5" stroke="${palette.secondary}" stroke-width="2.5" fill="${palette.secondary}" fill-opacity="0.2"/>
  <path d="M29 35.5H35" stroke="${palette.secondary}" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="23.5" cy="35.5" r="1.5" fill="${palette.secondary}"/>
  <circle cx="40.5" cy="35.5" r="1.5" fill="${palette.secondary}"/>

  <!-- Subtle Cybernetic Line -->
  <path d="M28 49Q32 51 36 49" stroke="${palette.primary}" stroke-width="2" stroke-linecap="round"/>
</svg>`
}

/**
 * Updates the document favicon link tag dynamically with the current palette SVG data URI.
 */
export function updateBrowserFavicon(palette: LogoPalette): void {
  if (typeof document === "undefined") return

  try {
    let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']")
    if (!link) {
      link = document.createElement("link")
      link.rel = "icon"
      document.head.appendChild(link)
    }

    const svgString = getChaiFaviconSvg(palette)
    const encoded = encodeURIComponent(svgString)
    link.type = "image/svg+xml"
    link.href = `data:image/svg+xml;utf8,${encoded}`
  } catch (err) {
    console.debug("Dynamic favicon notice:", err)
  }
}
