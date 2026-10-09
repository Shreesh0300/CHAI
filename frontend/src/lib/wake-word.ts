/**
 * "Hey CHAI" Wake Word Detection Engine
 *
 * Uses the browser's built-in SpeechRecognition API to continuously listen
 * for wake phrases like "Hey CHAI", "OK CHAI", "Hi CHAI", etc.
 *
 * When a wake word is detected:
 *  1. Fires the onWake callback with any trailing query text
 *  2. Optionally speaks an acknowledgement
 *  3. Transitions the assistant into active listening mode
 *
 * This runs entirely in the browser — no server-side daemon required.
 * Supabase backend integrity is fully preserved.
 */

// ─── Wake Phrase Patterns ────────────────────────────────────────────────────
const WAKE_PHRASES = [
  "hey chai",
  "hey chia",      // common misrecognition
  "hey try",       // common misrecognition
  "hey shy",       // common misrecognition
  "a chai",        // common misrecognition of "hey chai"
  "hi chai",
  "hello chai",
  "ok chai",
  "okay chai",
  "wake up chai",
  "welcome back chai",
  "chai wake up",
  "yo chai",
  // Hindi
  "नमस्ते चाई",
  "हे चाय",
  "सुनो चाई",
  // Kannada
  "ನಮಸ್ಕಾರ ಚಾಯ್",
  "ಹೇ ಚಾಯ್",
  "ಕೇಳು ಚಾಯ್",
] as const;

// Compile a regex from all wake phrases for fast matching
const WAKE_REGEX = new RegExp(
  `\\b(${WAKE_PHRASES.map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\b`,
  "i"
);

export interface WakeWordResult {
  /** The exact wake phrase that was matched */
  phrase: string;
  /** Any text spoken after the wake phrase (the user's command) */
  trailingQuery: string;
  /** Full transcript that triggered the wake */
  fullTranscript: string;
  /** Timestamp of detection */
  timestamp: number;
}

export interface WakeWordEngineOptions {
  /** Called when a wake word is detected */
  onWake: (result: WakeWordResult) => void;
  /** Called with live interim transcripts for UI display */
  onInterimTranscript?: (text: string) => void;
  /** Called when the engine starts/stops */
  onStateChange?: (isListening: boolean) => void;
  /** Language for recognition (default: "en-US") */
  language?: string;
  /** Cooldown period after detection before listening again (ms, default: 3000) */
  cooldownMs?: number;
  /** Whether to auto-start on creation (default: true) */
  autoStart?: boolean;
}

/**
 * Checks if a given transcript text contains a wake phrase.
 * Returns the match info or null if no wake phrase found.
 */
export function detectWakePhrase(text: string): WakeWordResult | null {
  if (!text || !text.trim()) return null;

  const lower = text.toLowerCase().trim();

  // Check each wake phrase
  for (const phrase of WAKE_PHRASES) {
    const idx = lower.indexOf(phrase);
    if (idx !== -1) {
      const trailingQuery = lower
        .slice(idx + phrase.length)
        .replace(/^[\s,;:.!?]+/, "")
        .trim();

      return {
        phrase,
        trailingQuery,
        fullTranscript: text.trim(),
        timestamp: Date.now(),
      };
    }
  }

  return null;
}

/**
 * Creates and manages a background wake word detection engine.
 * Returns control methods to start, stop, and query state.
 */
export function createWakeWordEngine(options: WakeWordEngineOptions) {
  const {
    onWake,
    onInterimTranscript,
    onStateChange,
    language = "en-US",
    cooldownMs = 3000,
    autoStart = true,
  } = options;

  let recognition: any = null;
  let isRunning = false;
  let isInCooldown = false;
  let cooldownTimer: ReturnType<typeof setTimeout> | null = null;
  let restartTimer: ReturnType<typeof setTimeout> | null = null;

  const SpeechRecognitionClass =
    typeof window !== "undefined"
      ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      : null;

  if (!SpeechRecognitionClass) {
    console.warn("[WakeWord] SpeechRecognition API not available in this browser.");
    return {
      start: () => {},
      stop: () => {},
      isActive: () => false,
      isSupported: false,
    };
  }

  function createRecognition() {
    const rec = new SpeechRecognitionClass();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = language;
    rec.maxAlternatives = 3;

    rec.onresult = (event: any) => {
      if (isInCooldown) return;

      let finalTranscript = "";
      let interimTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0]?.transcript || "";

        if (result.isFinal) {
          finalTranscript += text;
        } else {
          interimTranscript += text;
        }
      }

      // Report interim transcripts for UI
      if (interimTranscript && onInterimTranscript) {
        onInterimTranscript(interimTranscript);
      }

      // Check all alternatives for wake phrase (handles misrecognitions)
      const textsToCheck = [finalTranscript, interimTranscript];
      for (let i = event.resultIndex; i < event.results.length; i++) {
        for (let j = 0; j < event.results[i].length; j++) {
          const alt = event.results[i][j]?.transcript || "";
          if (alt && !textsToCheck.includes(alt)) {
            textsToCheck.push(alt);
          }
        }
      }

      for (const text of textsToCheck) {
        const wakeResult = detectWakePhrase(text);
        if (wakeResult) {
          console.log(`[WakeWord] 🎙️ WAKE DETECTED: "${wakeResult.phrase}" | Query: "${wakeResult.trailingQuery}"`);

          // Enter cooldown to prevent duplicate triggers
          isInCooldown = true;
          if (cooldownTimer) clearTimeout(cooldownTimer);
          cooldownTimer = setTimeout(() => {
            isInCooldown = false;
          }, cooldownMs);

          onWake(wakeResult);
          return; // Only fire once per detection cycle
        }
      }
    };

    rec.onerror = (event: any) => {
      const ignoredErrors = ["no-speech", "aborted"];
      if (!ignoredErrors.includes(event.error)) {
        console.warn(`[WakeWord] Recognition error: ${event.error}`);
      }
    };

    rec.onend = () => {
      // Auto-restart if we're supposed to be running
      if (isRunning && !isInCooldown) {
        if (restartTimer) clearTimeout(restartTimer);
        restartTimer = setTimeout(() => {
          if (isRunning) {
            try {
              createAndStart();
            } catch (e) {
              console.warn("[WakeWord] Failed to restart:", e);
            }
          }
        }, 250);
      }
    };

    return rec;
  }

  function createAndStart() {
    try {
      if (recognition) {
        try {
          recognition.abort();
        } catch {}
      }
      recognition = createRecognition();
      recognition.start();
    } catch (e) {
      console.warn("[WakeWord] Start error:", e);
    }
  }

  function start() {
    if (isRunning) return;
    isRunning = true;
    isInCooldown = false;
    onStateChange?.(true);
    createAndStart();
    console.log('[WakeWord] 🚀 Wake word engine started — say "Hey CHAI" to activate');
  }

  function stop() {
    isRunning = false;
    isInCooldown = false;
    if (cooldownTimer) {
      clearTimeout(cooldownTimer);
      cooldownTimer = null;
    }
    if (restartTimer) {
      clearTimeout(restartTimer);
      restartTimer = null;
    }
    if (recognition) {
      try {
        recognition.abort();
      } catch {}
      recognition = null;
    }
    onStateChange?.(false);
    console.log("[WakeWord] Wake word engine stopped");
  }

  if (autoStart) {
    // Slight delay to allow component mount
    setTimeout(start, 500);
  }

  return {
    start,
    stop,
    isActive: () => isRunning,
    isSupported: true,
  };
}
