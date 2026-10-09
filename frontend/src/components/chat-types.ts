export type AssistantMode = "ask" | "research" | "agent"
export type WorkspaceLayout = "chat" | "workspace"
export type MessageRole = "user" | "assistant"

export interface PromptInputMeta {
  model: string
  effort: string
  attachments: File[]
  isVoice?: boolean
  language?: string
}


export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  attachments?: string[]
}

export interface WorkMetric {
  label: string
  value: string
  change: string
  note: string
}

export interface WorkRow {
  source: string
  description: string
  share: number
  change: string
}

export interface WorkArtifact {
  title: string
  subtitle: string
  metrics: WorkMetric[]
  chartData: { week: string; current: number; benchmark: number }[]
  rows: WorkRow[]
  highlights: string[]
  nextSteps: string[]
}

export interface Conversation {
  id: string
  title: string
  messages: ChatMessage[]
  layout: WorkspaceLayout
  mode: AssistantMode
  work?: WorkArtifact
}

export interface PromptSuggestion {
  label: string
  detail: string
  mode: AssistantMode
  prompt: string
}

export const MODE_DETAILS: Record<AssistantMode, { label: string; description: string }> = {
  ask: {
    label: "Ask",
    description: "Quick answers stay in one clean conversation.",
  },
  research: {
    label: "Research",
    description: "A side workspace keeps research, data, and next steps together.",
  },
  agent: {
    label: "Agent",
    description: "Multi-step work opens beside your conversation for easy follow-up.",
  },
}

export const QUICK_PROMPTS: PromptSuggestion[] = [
  {
    label: "Explain a product roadmap simply",
    detail: "Quick answer",
    mode: "ask",
    prompt: "Explain a product roadmap in plain language.",
  },
  {
    label: "Review campaign performance",
    detail: "Research workspace",
    mode: "research",
    prompt: "Review this campaign performance snapshot with a trend chart, channel breakdown, and next steps.",
  },
  {
    label: "Build a growth action brief",
    detail: "Agent workspace",
    mode: "agent",
    prompt: "Create a growth action plan from this campaign performance snapshot, with milestones and measures of success.",
  },
]

export function shouldOpenWorkPane(
  prompt: string,
  mode: AssistantMode,
  attachmentCount = 0,
) {
  if (mode !== "ask" || attachmentCount > 0) return true

  const wordCount = prompt.trim().split(/\s+/).filter(Boolean).length
  const workSignals =
    /\b(report|dashboard|table|chart|visual|analytics|dataset|compare|comparison|breakdown|research|agent|performance|trend|forecast|data-heavy)\b/i

  return wordCount >= 34 || workSignals.test(prompt)
}

export function createWorkArtifact(prompt: string): WorkArtifact {
  const normalizedPrompt = prompt.toLowerCase()
  const title = normalizedPrompt.includes("launch") || normalizedPrompt.includes("campaign")
    ? "Campaign performance brief"
    : normalizedPrompt.includes("compare")
      ? "Comparison brief"
      : "Research brief"

  return {
    title,
    subtitle: "A focused overview with the key signals and next steps in one place.",
    metrics: [
      { label: "Qualified leads", value: "1,284", change: "+18%", note: "vs. prior period" },
      { label: "Cost per lead", value: "$24.80", change: "−12%", note: "vs. prior period" },
      { label: "Conversion rate", value: "8.6%", change: "+2.1 pts", note: "vs. prior period" },
    ],
    chartData: [
      { week: "Wk 1", current: 34, benchmark: 30 },
      { week: "Wk 2", current: 40, benchmark: 34 },
      { week: "Wk 3", current: 38, benchmark: 36 },
      { week: "Wk 4", current: 52, benchmark: 39 },
      { week: "Wk 5", current: 61, benchmark: 45 },
      { week: "Wk 6", current: 72, benchmark: 49 },
    ],
    rows: [
      { source: "Organic search", description: "Search-led discovery", share: 38, change: "+18%" },
      { source: "Partner referrals", description: "Qualified introductions", share: 27, change: "+11%" },
      { source: "Paid social", description: "Campaign traffic", share: 21, change: "+6%" },
      { source: "Email", description: "Returning audience", share: 14, change: "−3%" },
    ],
    highlights: [
      "Organic search is the strongest illustrative growth signal.",
      "Partner referrals contribute a meaningful share of qualified activity.",
      "The example data is labeled throughout and is not connected to a live source.",
    ],
    nextSteps: [
      "Confirm the source data and reporting period.",
      "Review the strongest and weakest contributing channels.",
      "Turn the findings into a short list of actions.",
    ],
  }
}

export function createAssistantReply(
  prompt: string,
  layout: WorkspaceLayout,
  isFollowUp: boolean,
) {
  const normalizedPrompt = prompt.trim().toLowerCase()

  if (layout === "workspace") {
    return isFollowUp
      ? "I've added that follow-up to the conversation. Keep refining the brief here, or ask another question from the work panel. The figures in the workspace are illustrative sample data."
      : "I've organized this into a focused work area with an overview, trend view, data table, and next steps. The figures are illustrative sample data, not live results."
  }

  if (/^(hi|hello|hey|good morning|good afternoon)[.! ]*$/.test(normalizedPrompt)) {
    return "Hi. What would you like to work through today?"
  }

  if (/\b(explain|what is|how does|define)\b/.test(normalizedPrompt)) {
    return "A simple way to think about it is to start with the outcome, name the few ideas that matter most, and connect each one to a practical example. Share the topic or audience and I can make the explanation more specific."
  }

  if (/\b(draft|write|word|email|message)\b/.test(normalizedPrompt)) {
    return "Here's a clear first pass:\n\nStart with the point you want the reader to remember. Add only the context they need, then close with one concrete next step. If you share the audience and tone, I can turn that outline into a finished draft."
  }

  return "A useful first pass is to define the outcome, identify the one or two constraints that matter, and choose a small next step. Share a little more context and I can tailor the answer to your situation."
}

export function createConversationTitle(prompt: string) {
  const title = prompt.trim().replace(/\s+/g, " ")
  const words = title.split(" ")
  return words.length > 7 ? `${words.slice(0, 7).join(" ")}…` : title
}

export function createId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function formatAttachmentPrompt(attachments: File[]) {
  if (attachments.length === 0) return ""
  return attachments.length === 1 ? "Review this attachment" : `Review these ${attachments.length} attachments`
}

export const EMPTY_PROMPT_META: PromptInputMeta = {
  model: "Auto",
  effort: "Balanced",
  attachments: [],
}

export const chartConfig = {
  current: {
    label: "Current signal",
    color: "var(--chart-1)",
  },
  benchmark: {
    label: "Benchmark",
    color: "var(--chart-2)",
  },
} as const
