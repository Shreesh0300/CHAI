import { useState } from "react"
import { FileText, Sparkles, Volume2, VolumeX } from "lucide-react"
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
  const [isSpeaking, setIsSpeaking] = useState(false)

  const handleSpeak = () => {
    if (typeof window === "undefined" || !window.speechSynthesis) return
    if (isSpeaking) {
      window.speechSynthesis.cancel()
      setIsSpeaking(false)
      return
    }

    window.speechSynthesis.cancel()
    const clean = message.content
      .replace(/```[\s\S]*?```/g, "Code block omitted.")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/[*_~#>]/g, "")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/\s+/g, " ")
      .trim()

    setTimeout(() => {
      const utterance = new SpeechSynthesisUtterance(clean)
      utterance.rate = 1.02
      const voices = window.speechSynthesis.getVoices()
      const voice =
        voices.find(
          (v) =>
            v.lang.startsWith("en") &&
            (v.name.includes("Natural") ||
              v.name.includes("Google") ||
              v.name.includes("Samantha") ||
              v.name.includes("Jenny") ||
              v.name.includes("Guy")),
        ) ||
        voices.find((v) => v.lang.startsWith("en")) ||
        voices[0]
      if (voice) utterance.voice = voice

      utterance.onstart = () => setIsSpeaking(true)
      utterance.onend = () => setIsSpeaking(false)
      utterance.onerror = () => setIsSpeaking(false)

      ;(window as any)._chaiRowUtterance = utterance
      if (window.speechSynthesis.paused) window.speechSynthesis.resume()
      window.speechSynthesis.speak(utterance)
    }, 50)
  }

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
        <div className="flex items-center justify-between w-full px-1 text-[11px] font-medium text-muted-foreground">
          <span>{isUser ? "You" : "CHAI"}</span>
          {!isUser && (
            <button
              type="button"
              onClick={handleSpeak}
              aria-label={isSpeaking ? "Stop voice" : "Read response aloud"}
              title={isSpeaking ? "Stop voice" : "Read response aloud"}
              className={cn(
                "flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] transition hover:bg-muted hover:text-foreground",
                isSpeaking && "text-primary font-semibold animate-pulse"
              )}
            >
              {isSpeaking ? <VolumeX className="size-3 text-destructive" /> : <Volume2 className="size-3" />}
              <span>{isSpeaking ? "Stop" : "Read aloud"}</span>
            </button>
          )}
        </div>
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
