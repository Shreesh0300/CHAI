import { Pause, Play, Square } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export interface GenerationControlsProps {
  isPaused: boolean
  onPause: () => void
  onResume: () => void
  onCancel: () => void
  disabled?: boolean
  compact?: boolean
  className?: string
}

/**
 * Active AI Generation toolbar providing Pause/Resume and Cancel controls.
 * Styled with CHAI's dark theme aesthetics and fully accessible.
 */
export function GenerationControls({
  isPaused,
  onPause,
  onResume,
  onCancel,
  disabled = false,
  compact = false,
  className,
}: GenerationControlsProps) {
  return (
    <div
      role="toolbar"
      aria-label="Generation controls"
      className={cn("inline-flex items-center gap-1.5", className)}
    >
      {isPaused ? (
        <Button
          type="button"
          variant="outline"
          size={compact ? "sm" : "sm"}
          onClick={onResume}
          disabled={disabled}
          aria-label="Resume generation"
          title="Resume active generation"
          className={cn(
            "h-7 gap-1.5 border-border/70 bg-card/80 px-2.5 text-xs font-medium text-foreground transition-all",
            "hover:border-emerald-500/40 hover:bg-emerald-500/10 hover:text-emerald-400 active:scale-95",
            compact && "h-6 px-2 text-[11px]",
          )}
        >
          <Play className="size-3 text-emerald-400 fill-emerald-400" aria-hidden="true" />
          <span>Resume</span>
        </Button>
      ) : (
        <Button
          type="button"
          variant="outline"
          size={compact ? "sm" : "sm"}
          onClick={onPause}
          disabled={disabled}
          aria-label="Pause generation"
          title="Pause active generation"
          className={cn(
            "h-7 gap-1.5 border-border/70 bg-card/80 px-2.5 text-xs font-medium text-foreground transition-all",
            "hover:border-amber-500/40 hover:bg-amber-500/10 hover:text-amber-400 active:scale-95",
            compact && "h-6 px-2 text-[11px]",
          )}
        >
          <Pause className="size-3 text-amber-400 fill-amber-400" aria-hidden="true" />
          <span>Pause</span>
        </Button>
      )}

      <Button
        type="button"
        variant="ghost"
        size={compact ? "sm" : "sm"}
        onClick={onCancel}
        disabled={disabled}
        aria-label="Cancel generation"
        title="Cancel active generation"
        className={cn(
          "h-7 gap-1.5 border border-border/40 bg-card/50 px-2.5 text-xs font-medium text-muted-foreground transition-all",
          "hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-400 active:scale-95",
          compact && "h-6 px-2 text-[11px]",
        )}
      >
        <Square className="size-3 text-rose-400 fill-rose-400" aria-hidden="true" />
        <span>Cancel</span>
      </Button>
    </div>
  )
}
