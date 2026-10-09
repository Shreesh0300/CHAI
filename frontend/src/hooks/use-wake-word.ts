/**
 * React hook for "Hey CHAI" wake word detection.
 *
 * Provides always-on background listening that detects wake phrases
 * and can automatically activate the voice assistant.
 *
 * Usage:
 * ```tsx
 * const { isWakeWordActive, lastWakeEvent, wakeWordSupported } = useWakeWord({
 *   onWake: (result) => {
 *     // Handle wake event - start listening, process query, etc.
 *     if (result.trailingQuery) {
 *       handleProcessQuery(result.trailingQuery);
 *     } else {
 *       startListening();
 *     }
 *   },
 *   enabled: true,
 * });
 * ```
 */

import { useEffect, useRef, useState, useCallback } from "react";
import {
  createWakeWordEngine,
  detectWakePhrase,
  type WakeWordResult,
} from "@/lib/wake-word";

export interface UseWakeWordOptions {
  /** Called when wake word is detected */
  onWake: (result: WakeWordResult) => void;
  /** Called with interim transcript text for real-time display */
  onInterimTranscript?: (text: string) => void;
  /** Whether wake word detection is enabled (default: true) */
  enabled?: boolean;
  /** Recognition language (default: "en-US") */
  language?: string;
  /** Cooldown after detection (ms, default: 4000) */
  cooldownMs?: number;
  /** Pause wake word when main voice recording is active */
  pauseWhileRecording?: boolean;
}

export function useWakeWord(options: UseWakeWordOptions) {
  const {
    onWake,
    onInterimTranscript,
    enabled = true,
    language = "en-US",
    cooldownMs = 4000,
    pauseWhileRecording = true,
  } = options;

  const [isWakeWordActive, setIsWakeWordActive] = useState(false);
  const [lastWakeEvent, setLastWakeEvent] = useState<WakeWordResult | null>(null);
  const [wakeWordSupported, setWakeWordSupported] = useState(true);

  const engineRef = useRef<ReturnType<typeof createWakeWordEngine> | null>(null);
  const onWakeRef = useRef(onWake);
  onWakeRef.current = onWake;

  const onInterimRef = useRef(onInterimTranscript);
  onInterimRef.current = onInterimTranscript;

  useEffect(() => {
    if (!enabled) {
      if (engineRef.current) {
        engineRef.current.stop();
        engineRef.current = null;
      }
      setIsWakeWordActive(false);
      return;
    }

    const engine = createWakeWordEngine({
      onWake: (result) => {
        setLastWakeEvent(result);
        onWakeRef.current(result);
      },
      onInterimTranscript: (text) => {
        onInterimRef.current?.(text);
      },
      onStateChange: (listening) => {
        setIsWakeWordActive(listening);
      },
      language,
      cooldownMs,
      autoStart: true,
    });

    engineRef.current = engine;
    setWakeWordSupported(engine.isSupported);

    return () => {
      engine.stop();
      engineRef.current = null;
    };
  }, [enabled, language, cooldownMs]);

  /** Temporarily pause wake word detection (e.g., while recording) */
  const pause = useCallback(() => {
    engineRef.current?.stop();
  }, []);

  /** Resume wake word detection after pause */
  const resume = useCallback(() => {
    if (enabled) {
      engineRef.current?.start();
    }
  }, [enabled]);

  return {
    /** Whether the wake word engine is currently listening */
    isWakeWordActive,
    /** The last detected wake event */
    lastWakeEvent,
    /** Whether the browser supports SpeechRecognition */
    wakeWordSupported,
    /** Temporarily pause detection */
    pause,
    /** Resume detection after pause */
    resume,
    /** Check if a given text contains a wake phrase */
    detectWakePhrase,
  };
}
