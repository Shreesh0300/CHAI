"use client"

import { useEffect, useMemo, useState } from "react"
import {
  Activity,
  Bot,
  CheckCircle2,
  CheckSquare,
  ChevronDown,
  Clock,
  Compass,
  Cpu,
  FileCheck2,
  GitMerge,
  Globe,
  Loader2,
  MinusCircle,
  Pause,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { GenerationControls } from "@/components/generation-controls"
import { cn } from "@/lib/utils"
import {
  AGENT_DESCRIPTIONS,
  AGENT_DISPLAY_NAMES,
  CANONICAL_SPECIALIST_AGENTS,
  FINALIZATION_AGENTS,
  type AgentExecutionInfo,
  type AgentExecutionStatus,
  type ExecutionTrackerState,
} from "@/components/chat-types"

interface AgentExecutionTrackerProps {
  state: ExecutionTrackerState
  isLive?: boolean
  defaultExpanded?: boolean
  className?: string
  isPaused?: boolean
  onPause?: () => void
  onResume?: () => void
  onCancel?: () => void
  selectedAgent?: string | null
  onSelectAgent?: (agentKey: string | null) => void
}

function formatDuration(ms?: number): string {
  if (ms === undefined || ms === null || isNaN(ms)) return ""
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function getAgentIcon(agentName: string) {
  switch (agentName) {
    case "information_acquisition":
      return Globe
    case "researcher":
      return Search
    case "strategist":
      return Compass
    case "engineer":
      return Cpu
    case "guardian":
      return ShieldAlert
    case "security":
      return ShieldCheck
    case "evaluator":
      return CheckSquare
    case "conflict_resolver":
      return GitMerge
    case "synthesizer":
      return Sparkles
    case "reliability_monitor":
      return Activity
    case "output_validator":
      return FileCheck2
    default:
      return Bot
  }
}

function StatusIndicator({
  status,
  durationMs,
  isLiveRunning,
}: {
  status: AgentExecutionStatus
  durationMs?: number
  isLiveRunning?: boolean
}) {
  switch (status) {
    case "running":
      return (
        <div className="flex items-center gap-1.5 font-mono text-[11px] font-medium text-primary">
          <Loader2 aria-hidden="true" className="size-3.5 animate-spin" />
          <span>Running</span>
          {durationMs !== undefined && durationMs > 0 && (
            <span className="text-muted-foreground">({formatDuration(durationMs)})</span>
          )}
        </div>
      )
    case "completed":
      return (
        <div className="flex items-center gap-1.5 font-mono text-[11px] font-medium text-emerald-500">
          <CheckCircle2 aria-hidden="true" className="size-3.5" />
          <span>Done</span>
          {durationMs !== undefined && (
            <span className="text-muted-foreground/80">({formatDuration(durationMs)})</span>
          )}
        </div>
      )
    case "failed":
      return (
        <div className="flex items-center gap-1.5 font-mono text-[11px] font-medium text-destructive">
          <XCircle aria-hidden="true" className="size-3.5" />
          <span>Failed</span>
        </div>
      )
    case "skipped":
      return (
        <div className="flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground/60">
          <MinusCircle aria-hidden="true" className="size-3.5" />
          <span>Skipped</span>
        </div>
      )
    case "pending":
    default:
      return (
        <div className="flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground/40">
          <Clock aria-hidden="true" className="size-3.5" />
          <span>Pending</span>
        </div>
      )
  }
}

export function AgentExecutionTracker({
  state,
  isLive = false,
  defaultExpanded,
  className,
  isPaused: isPausedProp = false,
  onPause,
  onResume,
  onCancel,
  selectedAgent,
  onSelectAgent,
}: AgentExecutionTrackerProps) {
  const isPaused = state.status === "paused" || Boolean(state.isPaused) || isPausedProp
  const isCancelled = state.status === "cancelled"
  const isRunning = state.status === "running" && !isPaused && !isCancelled
  const isCompleted = state.status === "completed"
  const isFailed = state.status === "failed"

  // User manual expand toggle state:
  // When running: open by default.
  // When completed: collapsed by default into summary banner unless user toggles or defaultExpanded is specified.
  const [isExpanded, setIsExpanded] = useState<boolean>(() => {
    if (defaultExpanded !== undefined) return defaultExpanded
    return isRunning
  })

  // Live timer tick for active duration calculation
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!isRunning || !isLive || isPaused) return
    const interval = setInterval(() => {
      setNow(Date.now())
    }, 150)
    return () => clearInterval(interval)
  }, [isRunning, isLive, isPaused])

  const totalElapsed = useMemo(() => {
    if (state.totalDurationMs !== undefined) return state.totalDurationMs
    if (state.startedAt) {
      const end = state.completedAt || (isRunning ? now : Date.now())
      return Math.max(0, end - state.startedAt)
    }
    return undefined
  }, [state.totalDurationMs, state.startedAt, state.completedAt, isRunning, now])

  // Partition agents into Specialists and Finalization
  const { specialists, finalizers } = useMemo(() => {
    const specList: AgentExecutionInfo[] = []
    const finList: AgentExecutionInfo[] = []

    const selectedSet = new Set(state.selectedAgents)
    const allKnown = new Set([
      ...CANONICAL_SPECIALIST_AGENTS,
      ...FINALIZATION_AGENTS,
      ...Object.keys(state.agents),
    ])

    // Order specialists canonically
    for (const name of CANONICAL_SPECIALIST_AGENTS) {
      if (allKnown.has(name)) {
        const info = state.agents[name]
        const isSelected = selectedSet.size === 0 || selectedSet.has(name)
        specList.push(
          info || {
            agent: name,
            displayName: AGENT_DISPLAY_NAMES[name] || name,
            description: AGENT_DESCRIPTIONS[name] || "",
            status: isSelected ? "pending" : "skipped",
            isFinalization: false,
          },
        )
      }
    }

    // Order finalization canonically
    for (const name of FINALIZATION_AGENTS) {
      if (allKnown.has(name)) {
        const info = state.agents[name]
        const isSelected = selectedSet.size === 0 || selectedSet.has(name)
        finList.push(
          info || {
            agent: name,
            displayName: AGENT_DISPLAY_NAMES[name] || name,
            description: AGENT_DESCRIPTIONS[name] || "",
            status: isSelected ? "pending" : "skipped",
            isFinalization: true,
          },
        )
      }
    }

    return { specialists: specList, finalizers: finList }
  }, [state.agents, state.selectedAgents])

  // Counts
  const completedSpecialists = specialists.filter((a) => a.status === "completed").length
  const completedFinalizers = finalizers.filter((a) => a.status === "completed").length
  const totalCompleted = completedSpecialists + completedFinalizers

  const activeAgent = useMemo(() => {
    for (const item of [...specialists, ...finalizers]) {
      if (item.status === "running") return item
    }
    return null
  }, [specialists, finalizers])

  return (
    <div
      role="region"
      aria-label="Multi-agent execution tracker"
      className={cn(
        "group relative w-full overflow-hidden rounded-2xl border transition-all duration-300",
        isRunning
          ? "border-primary/40 bg-card/95 shadow-lg shadow-primary/5 ring-1 ring-primary/20"
          : isFailed
            ? "border-destructive/40 bg-card/95 ring-1 ring-destructive/20"
            : "border-border/80 bg-card/80 hover:border-border hover:bg-card/95",
        className,
      )}
    >
      {/* Top Header / Banner Bar */}
      <div
        className={cn(
          "flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-5",
          isExpanded && "border-b border-border/60 bg-muted/20",
        )}
      >
        <div className="flex min-w-0 items-center gap-3">
          <div
            className={cn(
              "grid size-8 shrink-0 place-items-center rounded-xl transition-colors",
              isPaused
                ? "bg-amber-500/10 border border-amber-500/30 text-amber-400"
                : isCancelled
                  ? "bg-muted border border-border/80 text-muted-foreground"
                  : isRunning
                    ? "bg-primary text-primary-foreground shadow-sm shadow-primary/30"
                    : isFailed
                      ? "bg-destructive text-destructive-foreground"
                      : "bg-muted text-foreground border border-border/80",
            )}
          >
            {isPaused ? (
              <Pause aria-hidden="true" className="size-4 text-amber-400 fill-amber-400" />
            ) : isCancelled ? (
              <MinusCircle aria-hidden="true" className="size-4 text-rose-400" />
            ) : isRunning ? (
              <Sparkles aria-hidden="true" className="size-4 animate-pulse" />
            ) : isFailed ? (
              <XCircle aria-hidden="true" className="size-4" />
            ) : (
              <CheckCircle2 aria-hidden="true" className="size-4 text-emerald-500" />
            )}
          </div>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold tracking-tight text-foreground">
                {isPaused
                  ? "Execution paused at safe boundary"
                  : isCancelled
                    ? "Execution cancelled by user"
                    : isRunning
                      ? "CHAI is coordinating its agents"
                      : isFailed
                        ? "Execution encountered an error"
                        : `Coordinated ${totalCompleted} agents`}
              </span>

              {state.domain && (
                <span className="rounded-md border border-border/60 bg-muted/60 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
                  Lens: {state.domain}
                </span>
              )}
            </div>

            <p className="truncate text-[11px] text-muted-foreground">
              {isPaused
                ? "Agent scheduling suspended. Press Resume to continue."
                : isCancelled
                  ? "Generation was cancelled. Unfinished stages were stopped."
                  : isRunning
                    ? activeAgent
                      ? `Active: ${activeAgent.displayName} · ${activeAgent.description}`
                      : "Dispatching specialized reasoning agents..."
                    : isFailed
                      ? state.error || "One or more agents failed to complete"
                      : `All stages completed ${totalElapsed ? `in ${formatDuration(totalElapsed)}` : ""}`}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2.5">
          {isLive && (isRunning || isPaused) && (onPause || onResume || onCancel) && (
            <GenerationControls
              isPaused={isPaused}
              onPause={onPause || (() => {})}
              onResume={onResume || (() => {})}
              onCancel={onCancel || (() => {})}
              compact
            />
          )}

          {totalElapsed !== undefined && (
            <span className="font-mono text-xs text-muted-foreground">
              {formatDuration(totalElapsed)}
            </span>
          )}

          <Badge
            variant="outline"
            className={cn(
              "gap-1 font-mono text-[11px] font-normal transition-colors",
              isPaused && "border-amber-500/40 bg-amber-500/10 text-amber-400",
              isCancelled && "border-muted-foreground/30 bg-muted/40 text-muted-foreground",
              isRunning && "border-primary/40 bg-primary/10 text-primary",
              isCompleted && "border-emerald-500/30 bg-emerald-500/10 text-emerald-500",
              isFailed && "border-destructive/40 bg-destructive/10 text-destructive",
            )}
          >
            {isPaused && <Pause aria-hidden="true" className="size-3 text-amber-400 fill-amber-400" />}
            {isCancelled && <MinusCircle aria-hidden="true" className="size-3" />}
            {isRunning && <Loader2 aria-hidden="true" className="size-3 animate-spin" />}
            {isCompleted && <CheckCircle2 aria-hidden="true" className="size-3" />}
            {isFailed && <XCircle aria-hidden="true" className="size-3" />}
            <span>
              {isPaused
                ? "Paused"
                : isCancelled
                  ? "Cancelled"
                  : isRunning
                    ? "Running"
                    : isCompleted
                      ? "Completed"
                      : "Failed"}
            </span>
          </Badge>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-expanded={isExpanded}
            aria-label={isExpanded ? "Collapse agent execution details" : "Expand agent execution details"}
            onClick={() => setIsExpanded((prev) => !prev)}
            className="size-8 p-0 text-muted-foreground hover:text-foreground"
          >
            <ChevronDown
              aria-hidden="true"
              className={cn("size-4 transition-transform duration-200", isExpanded && "rotate-180")}
            />
          </Button>
        </div>
      </div>

      {/* Expanded Breakdown */}
      {isExpanded && (
        <div className="space-y-5 p-4 sm:p-5">
          {/* Section 1: Specialist Reasoning Agents */}
          <section aria-label="Specialist Agents" className="space-y-2.5">
            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Specialist Agents
              </span>
              <span className="font-mono text-[10px] text-muted-foreground">
                {completedSpecialists}/{specialists.length} completed
              </span>
            </div>

            {onSelectAgent && (
              <div className="flex items-center gap-1.5 rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-1.5 text-[10.5px] text-muted-foreground">
                <Sparkles className="size-3 text-primary shrink-0 animate-pulse" />
                <span>Tip: Click an agent to highlight their contributions in the answer canvas</span>
              </div>
            )}

            <div className="grid gap-2 sm:grid-cols-2">
              {specialists.map((agent) => {
                const Icon = getAgentIcon(agent.agent)
                return (
                  <AgentCard
                    key={agent.agent}
                    agent={agent}
                    Icon={Icon}
                    isLive={isLive && isRunning}
                    isSelected={selectedAgent === agent.agent}
                    onSelect={() => {
                      if (!onSelectAgent) return
                      onSelectAgent(selectedAgent === agent.agent ? null : agent.agent)
                    }}
                  />
                )
              })}
            </div>
          </section>

          {/* Section 2: Finalization & Synthesis Pipeline */}
          <section aria-label="Finalization Pipeline" className="space-y-2.5">
            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Finalization Pipeline
              </span>
              <span className="font-mono text-[10px] text-muted-foreground">
                {completedFinalizers}/{finalizers.length} completed
              </span>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              {finalizers.map((agent) => {
                const Icon = getAgentIcon(agent.agent)
                return (
                  <AgentCard
                    key={agent.agent}
                    agent={agent}
                    Icon={Icon}
                    isLive={isLive && isRunning}
                    isSelected={selectedAgent === agent.agent}
                    onSelect={() => {
                      if (!onSelectAgent) return
                      onSelectAgent(selectedAgent === agent.agent ? null : agent.agent)
                    }}
                  />
                )
              })}
            </div>
          </section>

          {/* Section 3: Final Answer State */}
          <section
            aria-label="Final Answer Stage"
            className="flex items-center justify-between rounded-xl border border-border/70 bg-muted/30 px-3.5 py-2.5 text-xs"
          >
            <div className="flex items-center gap-2.5">
              <span className="grid size-6 place-items-center rounded-md bg-background text-foreground border border-border/60">
                <Sparkles aria-hidden="true" className="size-3.5 text-primary" />
              </span>
              <div>
                <p className="font-medium text-foreground">Final Answer</p>
                <p className="text-[11px] text-muted-foreground">
                  Unified recommendation synthesized across all agents
                </p>
              </div>
            </div>

            <div>
              {isRunning ? (
                <div className="flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
                  <Clock aria-hidden="true" className="size-3.5 text-muted-foreground/60" />
                  <span>Waiting</span>
                </div>
              ) : isFailed ? (
                <div className="flex items-center gap-1.5 font-mono text-[11px] text-destructive">
                  <XCircle aria-hidden="true" className="size-3.5" />
                  <span>Stopped</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 font-mono text-[11px] font-medium text-emerald-500">
                  <CheckCircle2 aria-hidden="true" className="size-3.5" />
                  <span>Ready</span>
                </div>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

function AgentCard({
  agent,
  Icon,
  isLive,
  isSelected = false,
  onSelect,
}: {
  agent: AgentExecutionInfo
  Icon: React.ComponentType<{ className?: string }>
  isLive: boolean
  isSelected?: boolean
  onSelect?: () => void
}) {
  const isRunning = agent.status === "running"
  const isFailed = agent.status === "failed"
  const isCompleted = agent.status === "completed"
  const isSkipped = agent.status === "skipped"
  const isClickable = Boolean(onSelect && (isCompleted || isRunning))

  return (
    <div
      role={isClickable ? "button" : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onClick={isClickable ? onSelect : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault()
                onSelect?.()
              }
            }
          : undefined
      }
      className={cn(
        "group/card flex flex-col justify-between gap-2 rounded-xl border p-3 transition-all select-none text-left",
        isClickable && "cursor-pointer",
        isSelected
          ? "border-primary bg-primary/10 shadow-sm ring-2 ring-primary/60"
          : isRunning
            ? "border-primary/50 bg-primary/5 shadow-xs ring-1 ring-primary/20"
            : isFailed
              ? "border-destructive/40 bg-destructive/5"
              : isCompleted
                ? cn(
                    "border-border/80 bg-card/60",
                    isClickable && "hover:border-primary/60 hover:bg-primary/5 hover:shadow-xs",
                  )
                : isSkipped
                  ? "border-border/40 bg-muted/20 opacity-60"
                  : "border-border/60 bg-muted/10 opacity-75",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <div
            className={cn(
              "grid size-7 shrink-0 place-items-center rounded-lg border transition-colors",
              isSelected
                ? "border-primary bg-primary text-primary-foreground shadow-xs"
                : isRunning
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : isFailed
                    ? "border-destructive/40 bg-destructive/10 text-destructive"
                    : isCompleted
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-500"
                      : "border-border/60 bg-muted text-muted-foreground",
            )}
          >
            <Icon className="size-3.5" />
          </div>

          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <p className="truncate text-xs font-semibold text-foreground">
                {agent.displayName}
              </p>
              {isSelected && (
                <span className="shrink-0 rounded bg-primary/20 px-1 py-0.2 text-[9px] font-semibold text-primary">
                  Active
                </span>
              )}
            </div>
            <p className="truncate text-[10.5px] text-muted-foreground">
              {agent.message || agent.description}
            </p>
          </div>
        </div>

        <div className="shrink-0 pt-0.5">
          <StatusIndicator
            status={agent.status}
            durationMs={agent.durationMs}
            isLiveRunning={isLive && isRunning}
          />
        </div>
      </div>

      {isSelected && (
        <div className="flex items-center gap-1 text-[10px] font-medium text-primary">
          <Sparkles className="size-3 animate-pulse" />
          <span>Highlighting insights on canvas</span>
        </div>
      )}

      {isClickable && !isSelected && isCompleted && (
        <div className="text-[9.5px] text-muted-foreground/60 transition-colors group-hover/card:text-muted-foreground">
          Click to highlight contributions
        </div>
      )}

      {isFailed && agent.error && (
        <div className="mt-1 rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-[10px] text-destructive leading-tight">
          {agent.error}
        </div>
      )}
    </div>
  )
}
