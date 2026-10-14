import React from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "@/lib/utils"
import { AGENT_DISPLAY_NAMES } from "@/components/chat-types"

interface MarkdownContentProps {
  content: string
  className?: string
  highlightedAgent?: string | null
}

const AGENT_KEYWORDS: Record<string, { titles: string[]; keywords: string[] }> = {
  researcher: {
    titles: ["research", "background", "findings", "context", "analysis", "information", "market", "landscape", "sources"],
    keywords: ["research", "findings", "data", "benchmark", "market", "study", "studies", "evidence", "trends", "context", "source", "survey", "landscape"],
  },
  information_acquisition: {
    titles: ["acquisition", "sources", "data gathering", "context", "inputs"],
    keywords: ["gather", "collected", "sources", "context", "retrieved", "query", "documents", "evidence"],
  },
  strategist: {
    titles: ["strategic", "strategy", "positioning", "priorities", "commercial", "business", "planning", "framework", "roadmap", "goals", "recommendation"],
    keywords: ["strategy", "strategic", "priority", "priorities", "positioning", "roadmap", "commercial", "business model", "vision", "milestone", "value proposition", "competitive", "market", "growth", "opportunity", "startup", "venture", "revenue"],
  },
  engineer: {
    titles: ["technical", "architecture", "implementation", "engineering", "execution", "system", "code", "infrastructure", "steps", "actionable", "stack"],
    keywords: ["technical", "architecture", "engineering", "implementation", "stack", "system", "components", "api", "backend", "frontend", "infrastructure", "pipeline", "deploy", "database", "practical", "execution", "next steps", "actionable"],
  },
  guardian: {
    titles: ["safety", "ethics", "guardrails", "risk", "mitigation", "well-being", "downside", "responsible", "protection", "compliance"],
    keywords: ["safety", "risk", "mitigate", "mitigation", "guardrail", "ethics", "ethical", "downside", "burnout", "reversibility", "protect", "failure", "safeguard", "contingency", "well-being", "stress", "worst-case", "savings", "runway"],
  },
  security: {
    titles: ["security", "cybersecurity", "compliance", "threats", "defenses", "vendor risk", "governance", "vulnerability"],
    keywords: ["security", "cybersecurity", "vulnerability", "encryption", "auth", "authentication", "threat", "mitigations", "vendor risk", "privacy", "gdpr", "compliance", "defenses"],
  },
  evaluator: {
    titles: ["evaluation", "trade-off", "tradeoffs", "feasibility", "scoring", "assessment", "comparison", "pros and cons", "verdict", "decision matrix"],
    keywords: ["trade-off", "tradeoff", "evaluation", "score", "feasibility", "cost-benefit", "pros", "cons", "weigh", "compare", "comparison", "verdict", "assessment", "criteria", "decision framework"],
  },
  conflict_resolver: {
    titles: ["conflict", "reconciliation", "resolved conflicts", "alignment", "arbitration"],
    keywords: ["conflict", "contradiction", "reconcile", "reconciliation", "arbitrate", "disagreement", "alignment", "balanced", "opposing"],
  },
  synthesizer: {
    titles: ["synthesis", "unified", "summary", "conclusion", "final recommendation", "executive summary"],
    keywords: ["synthesis", "synthesized", "unified", "summary", "overall", "comprehensive", "in conclusion", "recommendation"],
  },
  reliability_monitor: {
    titles: ["reliability", "monitoring", "stability", "health"],
    keywords: ["reliability", "latency", "uptime", "monitor", "telemetry", "metrics", "health check"],
  },
  output_validator: {
    titles: ["validation", "verification", "quality", "audit"],
    keywords: ["validate", "validation", "verified", "quality check", "schema", "audit", "accurate"],
  },
}

function extractNodeText(node: React.ReactNode): string {
  if (typeof node === "string") return node
  if (typeof node === "number") return String(node)
  if (!node) return ""
  if (Array.isArray(node)) return node.map(extractNodeText).join(" ")
  if (React.isValidElement(node) && (node.props as any)?.children) {
    return extractNodeText((node.props as any).children)
  }
  return ""
}

function matchesAgent(text: string, agentKey?: string | null): boolean {
  if (!agentKey || !text) return false
  const config = AGENT_KEYWORDS[agentKey.toLowerCase()]
  if (!config) return false
  const lower = text.toLowerCase()

  if (lower.includes(agentKey.toLowerCase())) return true
  if (config.titles.some((t) => lower.includes(t))) return true

  let keywordMatches = 0
  for (const kw of config.keywords) {
    if (lower.includes(kw)) {
      keywordMatches++
      if (keywordMatches >= 2 || kw.length > 9) return true
    }
  }
  return false
}

export function MarkdownContent({ content, className, highlightedAgent }: MarkdownContentProps) {
  if (!content) return null

  const agentDisplayName = highlightedAgent ? AGENT_DISPLAY_NAMES[highlightedAgent] || highlightedAgent : ""

  return (
    <div className={cn("markdown-body text-foreground max-w-none space-y-3", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children, ...props }) => (
            <h1
              className="mt-6 mb-3 text-2xl font-bold tracking-tight text-foreground sm:text-3xl first:mt-0"
              {...props}
            >
              {children}
            </h1>
          ),
          h2: ({ children, ...props }) => {
            const text = extractNodeText(children)
            const isHighlighted = highlightedAgent ? matchesAgent(text, highlightedAgent) : false
            return (
              <h2
                className={cn(
                  "mt-5 mb-2.5 text-xl font-bold tracking-tight text-foreground sm:text-2xl first:mt-0 border-b border-border/40 pb-1.5 transition-all duration-200",
                  isHighlighted && "border-primary bg-primary/10 pl-3 pr-2 py-1 rounded-r-lg ring-1 ring-primary/40",
                  highlightedAgent && !isHighlighted && "opacity-75",
                )}
                {...props}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span>{children}</span>
                  {isHighlighted && (
                    <span className="rounded-full bg-primary/20 text-primary border border-primary/30 px-2 py-0.5 text-[10px] font-mono tracking-wide font-medium">
                      {agentDisplayName} input
                    </span>
                  )}
                </div>
              </h2>
            )
          },
          h3: ({ children, ...props }) => {
            const text = extractNodeText(children)
            const isHighlighted = highlightedAgent ? matchesAgent(text, highlightedAgent) : false
            return (
              <h3
                className={cn(
                  "mt-4 mb-2 text-lg font-semibold tracking-tight text-foreground sm:text-xl first:mt-0 transition-all duration-200",
                  isHighlighted && "border-l-4 border-primary bg-primary/10 pl-3 pr-2 py-1 rounded-r-lg ring-1 ring-primary/40",
                  highlightedAgent && !isHighlighted && "opacity-75",
                )}
                {...props}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span>{children}</span>
                  {isHighlighted && (
                    <span className="rounded-full bg-primary/20 text-primary border border-primary/30 px-2 py-0.5 text-[10px] font-mono tracking-wide font-medium">
                      {agentDisplayName}
                    </span>
                  )}
                </div>
              </h3>
            )
          },
          h4: ({ children, ...props }) => (
            <h4
              className="mt-3 mb-1.5 text-base font-semibold text-foreground first:mt-0"
              {...props}
            >
              {children}
            </h4>
          ),
          p: ({ children, ...props }) => {
            const text = extractNodeText(children)
            const isHighlighted = highlightedAgent ? matchesAgent(text, highlightedAgent) : false
            return (
              <p
                className={cn(
                  "mb-3 leading-7 text-foreground/90 last:mb-0 transition-all duration-200",
                  isHighlighted && "border-l-4 border-primary bg-primary/10 pl-3 pr-2 py-1.5 rounded-r-lg ring-1 ring-primary/30 shadow-xs",
                  highlightedAgent && !isHighlighted && "opacity-80",
                )}
                {...props}
              >
                {children}
              </p>
            )
          },
          strong: ({ children, ...props }) => (
            <strong className="font-semibold text-foreground" {...props}>
              {children}
            </strong>
          ),
          em: ({ children, ...props }) => (
            <em className="italic text-foreground/90" {...props}>
              {children}
            </em>
          ),
          ul: ({ children, ...props }) => (
            <ul className="my-2.5 ml-5 list-disc space-y-1.5 text-foreground/90" {...props}>
              {children}
            </ul>
          ),
          ol: ({ children, ...props }) => (
            <ol className="my-2.5 ml-5 list-decimal space-y-1.5 text-foreground/90" {...props}>
              {children}
            </ol>
          ),
          li: ({ children, ...props }) => (
            <li className="leading-7" {...props}>
              {children}
            </li>
          ),
          blockquote: ({ children, ...props }) => (
            <blockquote
              className="my-3.5 border-l-4 border-primary/70 bg-muted/30 py-1.5 pl-4 pr-3 italic text-muted-foreground rounded-r"
              {...props}
            >
              {children}
            </blockquote>
          ),
          a: ({ href, children, ...props }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-primary underline underline-offset-4 hover:text-primary/80 transition-colors"
              {...props}
            >
              {children}
            </a>
          ),
          table: ({ children, ...props }) => (
            <div className="my-4 w-full overflow-x-auto rounded-xl border border-border/80 shadow-xs">
              <table className="w-full border-collapse text-left text-sm" {...props}>
                {children}
              </table>
            </div>
          ),
          thead: ({ children, ...props }) => (
            <thead className="border-b border-border bg-muted/60 text-xs uppercase font-semibold text-foreground" {...props}>
              {children}
            </thead>
          ),
          tbody: ({ children, ...props }) => (
            <tbody className="divide-y divide-border/50 bg-card" {...props}>
              {children}
            </tbody>
          ),
          tr: ({ children, ...props }) => (
            <tr className="transition-colors hover:bg-muted/30" {...props}>
              {children}
            </tr>
          ),
          th: ({ children, ...props }) => (
            <th className="px-4 py-2.5 font-semibold text-foreground" {...props}>
              {children}
            </th>
          ),
          td: ({ children, ...props }) => (
            <td className="px-4 py-2.5 text-foreground/90" {...props}>
              {children}
            </td>
          ),
          hr: ({ ...props }) => (
            <hr className="my-5 border-border/70" {...props} />
          ),
          code: ({ node, className, children, ...props }: any) => {
            const match = /language-(\w+)/.exec(className || "")
            const isCodeBlock = Boolean(match) || (typeof children === "string" && children.includes("\n"))

            if (!isCodeBlock) {
              return (
                <code
                  className="rounded-md border border-border/60 bg-muted/80 px-1.5 py-0.5 font-mono text-[0.875em] font-medium text-foreground"
                  {...props}
                >
                  {children}
                </code>
              )
            }

            return (
              <div className="relative my-3.5 overflow-hidden rounded-xl border border-border/80 bg-zinc-950 font-mono text-xs shadow-sm">
                {match && (
                  <div className="flex items-center justify-between border-b border-border/30 bg-zinc-900/90 px-3.5 py-1.5 text-[11px] font-medium text-zinc-400 tracking-wide uppercase">
                    <span>{match[1]}</span>
                  </div>
                )}
                <pre className="overflow-x-auto p-4 text-zinc-100 leading-relaxed">
                  <code className={className} {...props}>
                    {children}
                  </code>
                </pre>
              </div>
            )
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
export default MarkdownContent
