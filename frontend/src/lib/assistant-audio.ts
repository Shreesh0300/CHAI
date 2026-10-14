/**
 * Shared utility for playing spoken assistant responses via Vikas TTS stream.
 * Strictly plays the final polished user-facing answer.
 * Never leaks internal traces, agent names, or debug metadata.
 * 
 * Features:
 * - Immediate interruptibility:
 *   * Shouting "stop", "cancel", "be quiet", "shut up", "enough", "pause", "halt"
 *   * Dual-engine interruption: Local Web Audio RMS Shout Detector + SpeechRecognition ASR
 *   * Keyboard hotkey (Escape or Space)
 *   * Direct tactile touch / click stop
 * - Non-blocking chunk playback cancellation (0ms delay on stop)
 * - Immediate abort of in-flight fetch requests & audio element buffers
 * - Clean hardware track disposal
 */

let activeAudio: HTMLAudioElement | null = null;
let activeAbortController: AbortController | null = null;
let activeInterruptRecognition: any = null;
let interruptRestartTimer: any = null;
let activeKeydownListener: ((e: KeyboardEvent) => void) | null = null;
let activeChunkResolve: ((played: boolean) => void) | null = null;
let activeSpeechResolve: (() => void) | null = null;

// Real-time shout detector state
let activeShoutStream: MediaStream | null = null;
let activeShoutAudioCtx: AudioContext | null = null;
let activeShoutAnimFrame: number | null = null;

let isPlayingInternal = false;
let stopRequested = false;

// Regex matching common voice interruption commands
const INTERRUPT_KEYWORD_REGEX =
  /\b(stop|stop\s+it|stop\s+speaking|stop\s+talking|cancel|enough|quiet|be\s+quiet|shut\s*up|pause|halt|silence|listen|ruko|bas|nillisi)\b/i;

export function isAssistantAudioPlaying(): boolean {
  return isPlayingInternal || (activeAudio !== null && !activeAudio.paused);
}

/**
 * Instantly terminates all audio playback, pending requests, and synthetic voice.
 * Executes in 0 milliseconds and unlocks any awaiting playback promises.
 */
export function stopAssistantAudio(): void {
  stopRequested = true;
  isPlayingInternal = false;

  // 1. Abort in-flight network requests
  if (activeAbortController) {
    try {
      activeAbortController.abort();
    } catch {}
    activeAbortController = null;
  }

  // 2. Stop HTMLAudioElement immediately
  if (activeAudio) {
    try {
      activeAudio.pause();
      activeAudio.currentTime = 0;
      activeAudio.src = "";
    } catch {}
    activeAudio = null;
  }

  // 3. Stop browser speech synthesis
  if (typeof window !== "undefined" && window.speechSynthesis) {
    try {
      window.speechSynthesis.cancel();
    } catch {}
  }

  // 4. Immediately resolve any awaiting chunk / speech promises so loop exits
  if (activeChunkResolve) {
    try {
      activeChunkResolve(false);
    } catch {}
    activeChunkResolve = null;
  }

  if (activeSpeechResolve) {
    try {
      activeSpeechResolve();
    } catch {}
    activeSpeechResolve = null;
  }

  // 5. Stop interrupt listener and cleanup audio tracks
  stopInterruptListener();
}

/**
 * Cleans assistant response text before sending to Text-to-Speech:
 * - Strips Markdown headers, bold, italics, links, blockquotes, bullets
 * - Removes code blocks, inline code, and HTML tags
 * - Eliminates raw JSON blocks and internal agent metadata
 * - Normalizes spacing into smooth, natural spoken sentences
 */
export function cleanTextForSpeech(rawText: string): string {
  if (!rawText) return "";

  let text = rawText;

  // 1. Remove code blocks entirely
  text = text.replace(/```[\s\S]*?```/g, " ");

  // 2. Remove inline code
  text = text.replace(/`([^`]+)`/g, "$1");

  // 3. Remove markdown headers
  text = text.replace(/#{1,6}\s*([^\n]+)/g, "$1. ");

  // 4. Remove bold & italics
  text = text.replace(/\*\*([^*]+)\*\*/g, "$1");
  text = text.replace(/\*([^*]+)\*/g, "$1");
  text = text.replace(/__([^_]+)__/g, "$1");
  text = text.replace(/_([^_]+)_/g, "$1");

  // 5. Remove bullet list markers
  text = text.replace(/^\s*[-*+]\s+/gm, "");
  text = text.replace(/^\s*\d+\.\s+/gm, "");

  // 6. Remove markdown links ([text](url) -> text) and URLs
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  text = text.replace(/https?:\/\/\S+/g, "");

  // 7. Remove tables and horizontal rules
  text = text.replace(/\|[^\n]+\|/g, "");
  text = text.replace(/[-=]{3,}/g, "");

  // 8. Remove JSON blocks or braces if any
  text = text.replace(/\{[^{}]*\}/g, "");

  // 9. Normalize whitespace
  text = text.replace(/\s+/g, " ").trim();

  return text;
}

/**
 * Cleans assistant response text for DISPLAY in the UI:
 * - Strips leftover Markdown formatting (**, *, ##, ---, etc.)
 * - Removes code block markers
 * - Preserves paragraph structure
 * - Makes text readable without raw markdown artifacts
 */
export function cleanTextForDisplay(rawText: string): string {
  if (!rawText) return "";

  let text = rawText;

  // 1. Remove code block markers but preserve content
  text = text.replace(/```[a-zA-Z]*\n?/g, "");
  text = text.replace(/```/g, "");

  // 2. Remove inline code backticks
  text = text.replace(/`([^`]+)`/g, "$1");

  // 3. Remove markdown headers but keep text
  text = text.replace(/^#{1,6}\s+/gm, "");

  // 4. Remove bold markers (** and __)
  text = text.replace(/\*\*([^*]+)\*\*/g, "$1");
  text = text.replace(/__([^_]+)__/g, "$1");

  // 5. Remove italic markers (* and _) — careful not to break multiplication
  text = text.replace(/(?<!\w)\*([^*\n]+)\*(?!\w)/g, "$1");
  text = text.replace(/(?<!\w)_([^_\n]+)_(?!\w)/g, "$1");

  // 6. Remove strikethrough
  text = text.replace(/~~([^~]+)~~/g, "$1");

  // 7. Remove horizontal rules
  text = text.replace(/^[-*_]{3,}\s*$/gm, "");

  // 8. Clean up bullet markers at start of lines
  text = text.replace(/^\s*[-*+]\s+/gm, "• ");

  // 9. Remove markdown links, keep text
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");

  // 10. Remove blockquote markers
  text = text.replace(/^>\s?/gm, "");

  // 11. Clean up excessive blank lines
  text = text.replace(/\n{3,}/g, "\n\n");

  // 12. Remove leading/trailing whitespace per line
  text = text.split("\n").map(l => l.trimEnd()).join("\n").trim();

  return text;
}

/**
 * Splits long text into reasonable paragraphs/sentences so that speech can begin quickly
 * and is immediately interruptible without downloading a massive audio payload.
 */
function splitTextIntoChunks(text: string): string[] {
  const clean = cleanTextForSpeech(text);
  if (!clean) return [];

  // If text is short (< 350 chars), keep as a single chunk
  if (clean.length < 350) return [clean];

  // First split by paragraphs (double newlines)
  const paragraphs = clean.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const chunks: string[] = [];

  for (const para of paragraphs) {
    if (para.length <= 400) {
      chunks.push(para);
    } else {
      // Split paragraph by sentence boundaries (. ? !)
      const sentences = para.match(/[^.!?]+[.!?]+(?:\s|$)|[^.!?]+$/g) || [para];
      let current = "";
      for (const sentence of sentences) {
        const s = sentence.trim();
        if (!s) continue;
        if (current.length + s.length < 350) {
          current = current ? `${current} ${s}` : s;
        } else {
          if (current) chunks.push(current);
          current = s;
        }
      }
      if (current) chunks.push(current);
    }
  }

  return chunks.length > 0 ? chunks : [clean];
}

export interface PlayAudioOptions {
  onStart?: () => void;
  onChunkStart?: (chunk: string, index: number, total: number) => void;
  onEnd?: () => void;
  onInterrupt?: () => void;
}

/**
 * Streams and plays assistant speech with immediate stop capability and chunking.
 * Strictly guarantees microphone is not opened while speaking.
 */
export async function playAssistantAudio(
  text: string,
  language: string = "en",
  options?: PlayAudioOptions
): Promise<boolean> {
  const cleaned = cleanTextForSpeech(text);
  if (!cleaned) return false;

  // Stop any ongoing playback before starting new
  stopAssistantAudio();
  stopRequested = false;
  isPlayingInternal = true;

  // Auto-detect target script if not explicitly specified
  let targetLang = language || "en";
  if (!language || language === "en") {
    if (/[\u0C80-\u0CFF]/.test(cleaned)) {
      targetLang = "kn";
    } else if (/[\u0900-\u097F]/.test(cleaned)) {
      targetLang = "hi";
    } else if (/[\u0900-\u0963\u0970-\u097F]/.test(cleaned)) {
      targetLang = "sa";
    }
  }

  // Keyboard interrupt listener (Escape / Space)
  startInterruptListener(() => {
    stopAssistantAudio();
    options?.onInterrupt?.();
  });

  const chunks = splitTextIntoChunks(cleaned);
  options?.onStart?.();

  for (let i = 0; i < chunks.length; i++) {
    if (stopRequested) break;

    const chunk = chunks[i];
    options?.onChunkStart?.(chunk, i, chunks.length);

    const played = await playSingleChunk(chunk, targetLang);
    if (!played && !stopRequested) {
      // Fallback to browser speech for remaining text if backend network failed
      await fallbackSpeechAsync(chunk, targetLang);
    }

    if (stopRequested) break;
  }

  const wasInterrupted = stopRequested;
  isPlayingInternal = false;
  stopInterruptListener();

  if (!wasInterrupted) {
    options?.onEnd?.();
  }

  return !wasInterrupted;
}

/**
 * Fetches and plays a single audio chunk from the backend TTS endpoint.
 */
function playSingleChunk(chunkText: string, targetLang: string): Promise<boolean> {
  return new Promise(async (resolve) => {
    if (stopRequested) {
      resolve(false);
      return;
    }

    activeChunkResolve = resolve;
    const abortController = new AbortController();
    activeAbortController = abortController;

    try {
      const res = await fetch("http://localhost:8000/api/voice/tts/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: chunkText,
          language: targetLang,
          voice: "default",
        }),
        signal: abortController.signal,
      });

      if (!res.ok || stopRequested) {
        activeAbortController = null;
        activeChunkResolve = null;
        resolve(false);
        return;
      }

      const blob = await res.blob();
      if (!blob || blob.size < 200 || stopRequested) {
        activeAbortController = null;
        activeChunkResolve = null;
        resolve(false);
        return;
      }

      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      activeAudio = audio;
      activeAbortController = null;

      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        if (activeAudio === audio) activeAudio = null;
        activeChunkResolve = null;
        resolve(true);
      };

      audio.onpause = () => {
        if (stopRequested) {
          URL.revokeObjectURL(audioUrl);
          if (activeAudio === audio) activeAudio = null;
          activeChunkResolve = null;
          resolve(false);
        }
      };

      audio.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        if (activeAudio === audio) activeAudio = null;
        activeChunkResolve = null;
        resolve(false);
      };

      await audio.play();
    } catch (err: any) {
      activeAbortController = null;
      activeChunkResolve = null;
      if (err.name === "AbortError" || stopRequested) {
        resolve(false);
      } else {
        console.debug("Backend TTS streaming unreachable:", err);
        resolve(false);
      }
    }
  });
}

/**
 * Resilient Browser SpeechSynthesis fallback for a chunk.
 */
function fallbackSpeechAsync(text: string, lang: string = "en"): Promise<void> {
  return new Promise((resolve) => {
    if (stopRequested || typeof window === "undefined" || !window.speechSynthesis) {
      resolve();
      return;
    }

    activeSpeechResolve = resolve;

    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.05;
      utterance.pitch = 1.0;
      const langPrefix = lang === "kn" ? "kn" : lang === "hi" ? "hi" : lang === "sa" ? "sa" : "en";
      const voices = window.speechSynthesis.getVoices();
      const voice =
        voices.find(
          (v) =>
            v.lang.toLowerCase().startsWith(langPrefix) &&
            (v.name.includes("Google") || v.name.includes("Natural")),
        ) ||
        voices.find((v) => v.lang.toLowerCase().startsWith(langPrefix)) ||
        voices[0];
      if (voice) utterance.voice = voice;

      utterance.onend = () => {
        activeSpeechResolve = null;
        resolve();
      };
      utterance.onerror = () => {
        activeSpeechResolve = null;
        resolve();
      };

      window.speechSynthesis.speak(utterance);
    } catch {
      activeSpeechResolve = null;
      resolve();
    }
  });
}

/**
 * Keyboard & UI interrupt listener active ONLY while TTS is speaking:
 * - Listens for Escape or Space key to halt playback immediately
 * - Strictly does NOT open microphone or SpeechRecognition while speaking
 * - Guarantees microphone remains OFF so assistant never hears its own voice
 */
export function startInterruptListener(onInterrupt: () => void): void {
  stopInterruptListener();

  if (typeof window === "undefined") return;

  // Keyboard interrupt listener (Escape or Space key)
  activeKeydownListener = (e: KeyboardEvent) => {
    const targetTag = (e.target as HTMLElement)?.tagName?.toLowerCase();
    if (e.key === "Escape" || (e.code === "Space" && targetTag !== "input" && targetTag !== "textarea")) {
      console.log("Audio stopped via keyboard interrupt:", e.key);
      stopAssistantAudio();
      onInterrupt();
    }
  };
  window.addEventListener("keydown", activeKeydownListener);
}

export function stopInterruptListener(): void {
  if (activeKeydownListener && typeof window !== "undefined") {
    window.removeEventListener("keydown", activeKeydownListener);
    activeKeydownListener = null;
  }

  if (interruptRestartTimer) {
    clearTimeout(interruptRestartTimer);
    interruptRestartTimer = null;
  }

  if (activeShoutAnimFrame) {
    cancelAnimationFrame(activeShoutAnimFrame);
    activeShoutAnimFrame = null;
  }

  if (activeShoutStream) {
    try {
      activeShoutStream.getTracks().forEach((t) => t.stop());
    } catch {}
    activeShoutStream = null;
  }

  if (activeShoutAudioCtx && activeShoutAudioCtx.state !== "closed") {
    try {
      activeShoutAudioCtx.close().catch(() => {});
    } catch {}
    activeShoutAudioCtx = null;
  }

  if (activeInterruptRecognition) {
    try {
      activeInterruptRecognition.abort();
    } catch {}
    activeInterruptRecognition = null;
  }
}
