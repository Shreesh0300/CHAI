"use client"

import React from "react"
import { useChaiTheme } from "@/hooks/use-chai-theme"
import { type LogoPalette, getLogoPalette } from "@/lib/brand-palette"
import { cn } from "@/lib/utils"

export type LogoVariant = "full" | "icon" | "compact" | "favicon"
export type LogoSize = "xs" | "sm" | "md" | "lg" | "xl"

export interface ChaiLogoProps {
  variant?: LogoVariant
  size?: LogoSize | number
  className?: string
  accent?: string // Optional override for preview or showcase
  isDark?: boolean // Optional override
  showTagline?: boolean
  onClick?: () => void
}

const SIZE_CONFIGS: Record<LogoSize, { iconSize: number; titleClass: string; taglineClass: string; gapClass: string }> = {
  xs: {
    iconSize: 20,
    titleClass: "text-xs font-bold tracking-wider",
    taglineClass: "text-[7.5px] tracking-[0.24em]",
    gapClass: "gap-1.5",
  },
  sm: {
    iconSize: 28,
    titleClass: "text-sm font-bold tracking-wider",
    taglineClass: "text-[8.5px] tracking-[0.26em]",
    gapClass: "gap-2",
  },
  md: {
    iconSize: 36,
    titleClass: "text-base font-bold tracking-wider",
    taglineClass: "text-[9.5px] tracking-[0.28em]",
    gapClass: "gap-2.5",
  },
  lg: {
    iconSize: 48,
    titleClass: "text-xl font-extrabold tracking-wider",
    taglineClass: "text-[11px] tracking-[0.3em]",
    gapClass: "gap-3",
  },
  xl: {
    iconSize: 64,
    titleClass: "text-2xl font-black tracking-wider",
    taglineClass: "text-xs tracking-[0.32em]",
    gapClass: "gap-3.5",
  },
}

export function ChaiLogo({
  variant = "full",
  size = "md",
  className,
  accent: overrideAccent,
  isDark: overrideIsDark,
  showTagline = true,
  onClick,
}: ChaiLogoProps) {
  const themeState = useChaiTheme()
  const activeIsDark = overrideIsDark !== undefined ? overrideIsDark : themeState.isDark
  const activeAccent = overrideAccent !== undefined ? overrideAccent : themeState.accent
  const palette: LogoPalette = getLogoPalette(activeAccent, activeIsDark)

  const sizeKey = typeof size === "string" ? size : "md"
  const sizeConfig = SIZE_CONFIGS[sizeKey]
  const iconPx = typeof size === "number" ? size : sizeConfig.iconSize

  const isFavicon = variant === "favicon"
  const isIconOnly = variant === "icon" || isFavicon
  const isCompact = variant === "compact"

  return (
    <div
      onClick={onClick}
      className={cn(
        "inline-flex items-center select-none transition-colors duration-300",
        sizeConfig.gapClass,
        onClick && "cursor-pointer",
        className,
      )}
      role="img"
      aria-label="CHAI Logo - Autonomous Intelligence Framework"
    >
      {/* ─── Vector Icon: Stylized AI Face + Glasses + Circuit Tree ─────────── */}
      <svg
        width={iconPx}
        height={iconPx}
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0 transition-all duration-300"
        style={{
          filter: `drop-shadow(0 2px 8px ${palette.secondary}22)`,
        }}
      >
        <title>CHAI AI Core</title>

        {/* Circuit-tree branches extending upward from head */}
        <g className="transition-colors duration-300">
          {/* Center trunk */}
          <path
            d="M50 34V15"
            stroke={palette.secondary}
            strokeWidth={isFavicon ? 4 : 2.6}
            strokeLinecap="round"
          />
          <circle cx="50" cy="11.5" r={isFavicon ? 3.8 : 2.8} fill={palette.secondary} />

          {/* Left main diagonal and vertical riser */}
          <path
            d="M50 28L34 20V12"
            stroke={palette.secondary}
            strokeWidth={isFavicon ? 3.5 : 2.2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="34" cy="9.5" r={isFavicon ? 3.4 : 2.5} fill={palette.secondary} />

          {/* Left horizontal spur */}
          <path
            d="M34 20L22 25H18"
            stroke={palette.secondary}
            strokeWidth={isFavicon ? 3 : 2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="15.5" cy="25" r={isFavicon ? 3 : 2.2} fill={palette.secondary} />

          {/* Right main diagonal and vertical riser */}
          <path
            d="M50 28L66 20V12"
            stroke={palette.secondary}
            strokeWidth={isFavicon ? 3.5 : 2.2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="66" cy="9.5" r={isFavicon ? 3.4 : 2.5} fill={palette.secondary} />

          {/* Right horizontal spur */}
          <path
            d="M66 20L78 25H82"
            stroke={palette.secondary}
            strokeWidth={isFavicon ? 3 : 2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="84.5" cy="25" r={isFavicon ? 3 : 2.2} fill={palette.secondary} />
        </g>

        {/* Stylized AI Face Silhouette Contour */}
        <path
          d="M32 38C23 44 22 62 25 71C28 80 39 88 50 92C61 88 72 80 75 71C78 62 77 44 68 38C59 33 41 33 32 38Z"
          stroke={palette.primary}
          strokeWidth={isFavicon ? 4 : 2.8}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
          className="transition-colors duration-300"
        />

        {/* High-Tech Glasses (Spectacles) */}
        {/* Left Smart Frame */}
        <rect
          x="30"
          y="49"
          width="16"
          height="13"
          rx="3.5"
          stroke={palette.secondary}
          strokeWidth={isFavicon ? 3.5 : 2.5}
          fill={palette.secondary}
          fillOpacity={activeIsDark ? 0.16 : 0.12}
          className="transition-all duration-300"
        />
        {/* Right Smart Frame */}
        <rect
          x="54"
          y="49"
          width="16"
          height="13"
          rx="3.5"
          stroke={palette.secondary}
          strokeWidth={isFavicon ? 3.5 : 2.5}
          fill={palette.secondary}
          fillOpacity={activeIsDark ? 0.16 : 0.12}
          className="transition-all duration-300"
        />
        {/* Bridge connecting frames */}
        <path
          d="M46 55.5H54"
          stroke={palette.secondary}
          strokeWidth={isFavicon ? 3.5 : 2.5}
          strokeLinecap="round"
          className="transition-colors duration-300"
        />
        {/* Outer Hinges extending to Temples */}
        <path
          d="M25 55.5H30"
          stroke={palette.secondary}
          strokeWidth={isFavicon ? 3 : 2}
          strokeLinecap="round"
          className="transition-colors duration-300"
        />
        <path
          d="M70 55.5H75"
          stroke={palette.secondary}
          strokeWidth={isFavicon ? 3 : 2}
          strokeLinecap="round"
          className="transition-colors duration-300"
        />

        {/* Subtle Tech Reticle Eye Pupils */}
        <circle cx="38" cy="55.5" r={isFavicon ? 2.4 : 1.8} fill={palette.secondary} />
        <circle cx="62" cy="55.5" r={isFavicon ? 2.4 : 1.8} fill={palette.secondary} />

        {/* Nose bridge and jaw contour accents (omitted in ultra-small favicon) */}
        {!isFavicon && (
          <>
            <path
              d="M50 58.5V67L47 69"
              stroke={palette.primary}
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeOpacity="0.7"
              className="transition-colors duration-300"
            />
            {/* Subtle Minimalist Mouth Line */}
            <path
              d="M43 76.5Q50 78.5 57 76.5"
              stroke={palette.primary}
              strokeWidth="2"
              strokeLinecap="round"
              strokeOpacity="0.8"
              className="transition-colors duration-300"
            />
          </>
        )}
      </svg>

      {/* ─── Typography: CHAI Wordmark & SINCE 2026 Tagline ─────────────────── */}
      {!isIconOnly && (
        <div className="flex flex-col leading-none justify-center">
          <span
            className={cn(sizeConfig.titleClass, "font-black tracking-[0.14em] uppercase transition-colors duration-300")}
            style={{ color: palette.primary }}
          >
            CHAI
          </span>

          {!isCompact && showTagline && (
            <span
              className={cn(sizeConfig.taglineClass, "font-semibold uppercase tracking-[0.28em] transition-colors duration-300 mt-0.5")}
              style={{ color: palette.tagline }}
            >
              SINCE 2026
            </span>
          )}
        </div>
      )}
    </div>
  )
}
