import { FileText, Sparkles } from "lucide-react"
import type { ChatMessage } from "@/components/chat-types"
import { AgentExecutionTracker } from "@/components/agent-execution-tracker"
import { MarkdownContent } from "@/components/markdown-content"
import {
  Attachment,
  AttachmentContent,
  AttachmentGroup,
  AttachmentMedia,
  AttachmentTitle,
} from "@/components/ui/attachment"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import {
  Message,
  MessageAvatar,
  MessageContent,
  MessageHeader,
} from "@/components/ui/message"
import { cn } from "@/lib/utils"

export function ChatMessageRow({
  message,
  selectedAgent,
  onSelectAgent,
}: {
  message: ChatMessage
  selectedAgent?: string | null
  onSelectAgent?: (agent: string | null) => void
}) {
  const isUser = message.role === "user"

  return (
    <Message
      align={isUser ? "end" : "start"}
      className={cn("items-start gap-2.5 sm:gap-3", isUser && "pl-8 sm:pl-16")}
    >
      {!isUser && (
        <MessageAvatar className="mt-5 size-8 rounded-lg bg-primary text-primary-foreground">
          <Sparkles aria-hidden="true" className="size-4" />
        </MessageAvatar>
      )}
      <MessageContent
        className={cn(
          "min-w-0 gap-1.5",
          isUser ? "max-w-[min(100%,700px)] items-end" : "max-w-[min(100%,740px)] items-start",
        )}
      >
        <MessageHeader className="flex items-center gap-2 px-1 text-[11px] font-medium text-muted-foreground">
          <span>{isUser ? "You" : "CHAI"}</span>
          {!isUser && message.resolved_domain && (
            <span className="rounded bg-muted/90 px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider text-muted-foreground border border-border/60">
              Domain: {message.resolved_domain}
            </span>
          )}
        </MessageHeader>

        {!isUser && message.executionTrackerState && (
          <div className="w-full mb-1">
            <AgentExecutionTracker
              state={message.executionTrackerState}
              isLive={false}
              defaultExpanded={false}
              selectedAgent={selectedAgent}
              onSelectAgent={onSelectAgent}
            />
          </div>
        )}

        <Bubble
          align={isUser ? "end" : "start"}
          variant={isUser ? "secondary" : "ghost"}
          className={cn("max-w-full", !isUser && "w-full")}
        >
          <BubbleContent
            className={cn(
              "break-words",
              isUser
                ? "whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-6"
                : "w-full rounded-2xl border border-border/80 bg-card px-4 py-3 text-sm text-card-foreground shadow-xs",
            )}
          >
            {isUser ? (
              message.content
            ) : (
              <MarkdownContent
                content={message.content}
                highlightedAgent={selectedAgent}
              />
            )}
          </BubbleContent>
        </Bubble>

        {isUser && message.attachments && message.attachments.length > 0 && (
          <AttachmentGroup
            aria-label="Attached files"
            className="max-w-full justify-end gap-2 px-1 pt-1"
          >
            {message.attachments.map((fileName, index) => (
              <Attachment
                key={`${fileName}-${index}`}
                size="xs"
                className="max-w-[200px] bg-card"
              >
                <AttachmentMedia>
                  <FileText aria-hidden="true" />
                </AttachmentMedia>
                <AttachmentContent>
                  <AttachmentTitle>{fileName}</AttachmentTitle>
                </AttachmentContent>
              </Attachment>
            ))}
          </AttachmentGroup>
        )}
      </MessageContent>
    </Message>
  )
}
