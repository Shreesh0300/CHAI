import { FileText, Sparkles } from "lucide-react"
import type { ChatMessage } from "@/components/chat-types"
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

export function ChatMessageRow({ message }: { message: ChatMessage }) {
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
        <MessageHeader className="px-1 text-[11px] font-medium text-muted-foreground">
          {isUser ? "You" : "CHAI"}
        </MessageHeader>
        <Bubble
          align={isUser ? "end" : "start"}
          variant={isUser ? "secondary" : "ghost"}
          className={cn("max-w-full", !isUser && "w-full")}
        >
          <BubbleContent
            className={cn(
              "whitespace-pre-wrap break-words",
              isUser
                ? "rounded-2xl px-4 py-2.5 text-sm leading-6"
                : "w-full rounded-2xl border border-border/80 bg-card px-4 py-3 text-sm leading-6 text-card-foreground shadow-xs",
            )}
          >
            {message.content}
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
