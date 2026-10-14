export type AssistantMode = "ask" | "research" | "agent"
export type WorkspaceLayout = "chat" | "workspace"
export type MessageRole = "user" | "assistant"
export type DomainCategory = "AUTO" | "BUSINESS" | "PERSONAL" | "SOFTWARE"

export interface PromptInputMeta {
  model: string
  effort: string
  category?: DomainCategory
  attachments: File[]
  isVoice?: boolean
  language?: string
}


export type AgentExecutionStatus = "pending" | "running" | "completed" | "failed" | "skipped"

export interface AgentExecutionInfo {
  agent: string
  displayName: string
  description: string
  status: AgentExecutionStatus
  durationMs?: number
  error?: string
  message?: string
  isFinalization: boolean
}

export interface ExecutionTrackerState {
  requestId: string
  mode: "chat" | "solve" | "unknown"
  status: "idle" | "running" | "completed" | "failed" | "paused" | "cancelled"
  isPaused?: boolean
  agents: Record<string, AgentExecutionInfo>
  selectedAgents: string[]
  domain?: string
  finalAnswer?: string
  error?: string
  totalDurationMs?: number
  startedAt?: number
  completedAt?: number
}

export const AGENT_DESCRIPTIONS: Record<string, string> = {
  router: "Classifying query complexity and active domain lens",
  information_acquisition: "Acquiring empirical external knowledge and data sources",
  researcher: "Gathering empirical evidence and domain research",
  strategist: "Formulating strategic options, commercial viability, and trade-offs",
  engineer: "Architecting system design, components, and technical specifications",
  guardian: "Evaluating safety risks, ethical boundaries, and privacy protection",
  security: "Auditing threat models, access controls, and security hardening",
  evaluator: "Evaluating feasibility, scoring trade-offs, and ranking options",
  conflict_resolver: "Reconciling conflicting perspectives across agent proposals",
  synthesizer: "Synthesizing unified, coherent recommendation",
  reliability_monitor: "Auditing factual grounding and reasoning reliability",
  output_validator: "Validating final response standards and contracts",
}

export const AGENT_DISPLAY_NAMES: Record<string, string> = {
  router: "Router",
  information_acquisition: "Information Acquisition",
  researcher: "Researcher Agent",
  strategist: "Strategist Agent",
  engineer: "Engineer Agent",
  guardian: "Guardian Agent",
  security: "Security Agent",
  evaluator: "Evaluator Agent",
  conflict_resolver: "Conflict Resolver",
  synthesizer: "Synthesizer Agent",
  reliability_monitor: "Reliability Monitor",
  output_validator: "Output Validator",
}

export const CANONICAL_SPECIALIST_AGENTS: string[] = [
  "information_acquisition",
  "researcher",
  "strategist",
  "engineer",
  "guardian",
  "security",
]

export const FINALIZATION_AGENTS: string[] = [
  "evaluator",
  "conflict_resolver",
  "synthesizer",
  "reliability_monitor",
  "output_validator",
]

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  attachments?: string[]
  domain?: string
  resolved_domain?: string
  selected_agents?: string[]
  requestId?: string
  executionTrackerState?: ExecutionTrackerState
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
  domain?: string
  resolved_domain?: string
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

export function cleanConversationTitle(rawTitle: string): string {
  if (!rawTitle) return "New Conversation"

  let text = String(rawTitle).trim()

  // Extract from LangChain/Gemini content block artifacts:
  // e.g. "[{'type': 'text', 'text': 'College Startup vs Job Decision'}]" or "[{'type': 'text', 'text': '..."
  const structuredMatch = text.match(/['"]text['"]\s*:\s*['"]([^'"]+)/)
  if (structuredMatch) {
    text = structuredMatch[1].trim()
  } else {
    // Strip leading `[{'type': 'text', 'text': '` or `[{"type": "text", "text": "`
    text = text.replace(/^\[\s*\{\s*['"]type['"]\s*:\s*['"]text['"]\s*,\s*['"]text['"]\s*:\s*['"]?/i, "")
    // Strip trailing `}]` or quotes
    text = text.replace(/['"]?\s*\}\s*\]$/i, "")
  }

  // Remove code fences or markdown
  text = text.replace(/^```[a-zA-Z]*\s*/i, "").replace(/\s*```$/i, "")
  // Remove prefixes like "Title:", "Topic:"
  text = text.replace(/^(?:title|topic|subject|conversation title)\s*:\s*/i, "")
  // Strip outer quotes and brackets
  text = text.replace(/^[\[\{\("\'“‘`]+|[\]\}\)"\'”’`]+$/g, "").trim()
  // Strip trailing punctuation
  text = text.replace(/[\.\,\;\:\…\-\s]+$/, "").trim()
  // Collapse whitespace
  text = text.replace(/\s+/g, " ").trim()

  return text || "New Conversation"
}

export function createConversationTitle(prompt: string): string {
  let cleaned = cleanConversationTitle(prompt || "").replace(/\s+/g, " ")
  if (!cleaned || cleaned === "New Conversation") return "New Conversation"

  // Remove greetings
  cleaned = cleaned.replace(/^(?:hi|hey|hello|greetings)[,! ]*(?:chai[,! ]*)?/i, "").trim()

  // Remove common conversational fillers and lead-ins (handles "Im", "I'm", "thinking to", etc.)
  const leadIns = [
    /^(?:can\s+you\s+(?:please\s+)?(?:tell\s+me|explain|help\s+me\s+with|help\s+me)|could\s+you|please)\s+/i,
    /^(?:i(?:'m|m|\s+am)?\s+(?:thinking\s+(?:about|of|to)|wondering\s+(?:about|if|to)|confused\s+(?:between|about)|trying\s+to|planning\s+to))\s+/i,
    /^(?:thinking\s+(?:about|of|to))\s+/i,
    /^(?:i\s+(?:want\s+to|need\s+to|would\s+like\s+to|wish\s+to))\s+/i,
    /^(?:what\s+(?:is|are)\s+the\s+best\s+way\s+to)\s+/i,
  ]
  for (const pattern of leadIns) {
    cleaned = cleaned.replace(pattern, "").trim()
  }

  const lower = (cleaned || prompt).toLowerCase()

  // Specific heuristic: College / Engineering dropout decisions
  if (/drop\s*out|dropping\s+out|dropout/i.test(lower)) {
    if (/engineer|enginner/i.test(lower)) {
      return "Dropping Out of Engineering Decision"
    }
    if (/college|university|school/i.test(lower)) {
      return "College Dropout Decision"
    }
    return "Dropping Out Decision"
  }

  // Specific heuristic: DSA / 24 hours / Marathon / Challenges
  if (/24\s*hours/i.test(lower) && /dsa/i.test(lower)) {
    return "24-Hour DSA Marathon"
  }
  if (/dsa/i.test(lower) && /(?:difficult|hard|struggling|exam|problem|prep)/i.test(lower)) {
    return "Overcoming DSA Challenges"
  }

  // Specific heuristic: Framework/language comparisons
  if (/fastapi/i.test(lower) && /django/i.test(lower)) {
    return "FastAPI vs. Django"
  }
  if (/college/i.test(lower) && /startup/i.test(lower)) {
    return "College vs. Startup Decision"
  }

  // Specific heuristic: AI Job Search Agent
  if (/job/i.test(lower) && (/(?:resume|agent)/i.test(lower))) {
    return "AI-Powered Job Search Agent"
  }

  // Specific heuristic: Python index error
  if (/index/i.test(lower) && /error/i.test(lower) && /python/i.test(lower)) {
    return "Fixing Python Index Errors"
  }

  // Specific heuristic: Error / Exception fixing
  const errMatch = cleaned.match(/([a-zA-Z0-9_\s]{3,30}\s+(?:error|exception))/i)
  if (errMatch) {
    const errWords = errMatch[1]
      .trim()
      .split(/\s+/)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(" ")
    return `Fixing ${errWords}`
  }

  // Specific heuristic: "X vs Y"
  const vsMatch = cleaned.match(/([A-Za-z0-9_\-\.]+)\s+(?:vs\.?|versus|and|or)\s+([A-Za-z0-9_\-\.]+)/i)
  if (vsMatch && /(?:between|compare|choose|versus|vs)/i.test(lower)) {
    const it1 = vsMatch[1].trim()
    const it2 = vsMatch[2].trim()
    return `${it1.charAt(0).toUpperCase() + it1.slice(1).toLowerCase()} vs. ${it2.charAt(0).toUpperCase() + it2.slice(1).toLowerCase()}`
  }

  // General word-based clean title: take up to 6 words
  const words = (cleaned || prompt.trim()).split(/\s+/)
  const chosenWords = words.slice(0, 6)
  const STOP_WORDS = new Set([
    "of", "to", "for", "with", "in", "on", "at", "by", "from", "about",
    "and", "or", "the", "a", "an", "is", "any", "all", "too", "much"
  ])
  while (chosenWords.length > 2 && STOP_WORDS.has(chosenWords[chosenWords.length - 1].toLowerCase().replace(/[,.!?;:]+$/, ""))) {
    chosenWords.pop()
  }

  const cleanWords = chosenWords.map((w, idx) => {
    const lowerW = w.toLowerCase().replace(/[,.!?;:]+$/, "")
    if (idx > 0 && ["a", "an", "the", "in", "on", "at", "for", "to", "of", "and", "but", "or"].includes(lowerW)) {
      return lowerW
    }
    return w.charAt(0).toUpperCase() + w.slice(1)
  })

  const result = cleanWords.join(" ").replace(/[,\.\!\?\:\;\…\-\s]+$/, "").trim()
  return (result ? result.charAt(0).toUpperCase() + result.slice(1) : "New Conversation")
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
  category: "AUTO",
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
