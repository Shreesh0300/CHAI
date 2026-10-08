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
 * Splits long text into reasonable paragraphs/sentences so that speech can begin quickly
 * and is immediately interruptible without downloading a massive audio payload.
 */
function splitTextIntoChunks(text: string): string[] {
  const clean = text.trim();
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
 */
export async function playAssistantAudio(
  text: string,
  language: string = "en",
  options?: PlayAudioOptions
): Promise<boolean> {
  const cleanText = text.trim();
  if (!cleanText) return false;

  // Stop any ongoing playback before starting new
  stopAssistantAudio();
  stopRequested = false;
  isPlayingInternal = true;

  // Auto-detect target script if not explicitly specified
  let targetLang = language || "en";
  if (!language || language === "en") {
    if (/[\u0C80-\u0CFF]/.test(cleanText)) {
      targetLang = "kn";
    } else if (/[\u0900-\u097F]/.test(cleanText)) {
      targetLang = "hi";
    } else if (/[\u0900-\u0963\u0970-\u097F]/.test(cleanText)) {
      targetLang = "sa";
    }
  }

  // Start dual-engine interrupt listener (Shout detector + SpeechRecognition + Hotkeys)
  startInterruptListener(() => {
    stopAssistantAudio();
    options?.onInterrupt?.();
  });

  const chunks = splitTextIntoChunks(cleanText);
  options?.onStart?.();

  for (let i = 0; i < chunks.length; i++) {
    if (stopRequested) break;

    const chunk = chunks[i];
    options?.onChunkStart?.(chunk, i, chunks.length);

    const played = await playSingleChunk(chunk, targetLang);
    if (!played && !stopRequested) {
      // Fallback to browser speech for remaining text if network failed
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
 * Dual-engine voice & keyboard interrupt listener active ONLY while TTS is speaking:
 * 1. Web Audio Shout / Energy Spike Detector (instant local hardware detection for shouting "stop")
 * 2. SpeechRecognition ASR for keyword detection ("stop", "cancel", "be quiet", etc.)
 * 3. Keyboard Escape / Space key hotkey
 */
export function startInterruptListener(onInterrupt: () => void): void {
  stopInterruptListener();

  if (typeof window === "undefined") return;

  // 1. Keyboard interrupt listener (Escape or Space key)
  activeKeydownListener = (e: KeyboardEvent) => {
    const targetTag = (e.target as HTMLElement)?.tagName?.toLowerCase();
    if (e.key === "Escape" || (e.code === "Space" && targetTag !== "input" && targetTag !== "textarea")) {
      console.log("Audio stopped via keyboard interrupt:", e.key);
      stopAssistantAudio();
      onInterrupt();
    }
  };
  window.addEventListener("keydown", activeKeydownListener);

  // 2. Real-time Web Audio Shout / Voice Break-in Detector (0ms latency local detector)
  if (navigator?.mediaDevices?.getUserMedia) {
    navigator.mediaDevices
      .getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      .then((stream) => {
        if (stopRequested || !isPlayingInternal) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        activeShoutStream = stream;
        const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
        const audioCtx = new AudioContextClass();
        activeShoutAudioCtx = audioCtx;

        const source = audioCtx.createMediaStreamSource(stream);
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.2; // very fast reaction to shouts
        source.connect(analyser);

        const timeData = new Uint8Array(analyser.frequencyBinCount);
        const startTime = Date.now();
        let consecutiveShoutFrames = 0;
        let baselineRms = 0.015;

        const checkShout = () => {
          if (stopRequested || !isPlayingInternal) return;

          analyser.getByteTimeDomainData(timeData);
          let sumSquares = 0;
          for (let i = 0; i < timeData.length; i++) {
            const norm = (timeData[i] - 128) / 128;
            sumSquares += norm * norm;
          }
          const rms = Math.sqrt(sumSquares / timeData.length);
          const elapsed = Date.now() - startTime;

          // Warmup: track baseline level in first 250ms
          if (elapsed < 250) {
            baselineRms = Math.max(baselineRms, rms);
          } else {
            // Adaptive shout threshold: must exceed baseline by 2.2x and be >= 0.045
            const shoutThreshold = Math.max(0.045, baselineRms * 2.2);
            if (rms >= shoutThreshold) {
              consecutiveShoutFrames++;
              if (consecutiveShoutFrames >= 2) {
                console.log("Voice shout interruption detected! Level:", rms, "Threshold:", shoutThreshold);
                stopAssistantAudio();
                onInterrupt();
                return;
              }
            } else {
              consecutiveShoutFrames = 0;
            }
          }

          activeShoutAnimFrame = requestAnimationFrame(checkShout);
        };

        activeShoutAnimFrame = requestAnimationFrame(checkShout);
      })
      .catch((err) => {
        console.debug("Shout detector stream note:", err);
      });
  }

  // 3. Browser SpeechRecognition voice keyword listener running in parallel
  const SpeechRecognitionClass =
    (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  if (!SpeechRecognitionClass) return;

  function launchRecognition() {
    if (stopRequested || !isPlayingInternal) return;

    try {
      const recognition = new SpeechRecognitionClass();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 3;
      recognition.lang = navigator.language || "en-US";

      recognition.onresult = (event: any) => {
        let combined = "";
        for (let i = 0; i < event.results.length; i++) {
          for (let j = 0; j < event.results[i].length; j++) {
            const part = event.results[i][j].transcript || "";
            combined += " " + part;
          }
        }

        const normalized = combined.toLowerCase().trim();
        if (INTERRUPT_KEYWORD_REGEX.test(normalized)) {
          console.log("Voice interruption keyword detected ('stop' spoken):", normalized);
          stopAssistantAudio();
          try {
            recognition.stop();
          } catch {}
          onInterrupt();
        }
      };

      recognition.onerror = (e: any) => {
        console.debug("Interrupt recognition notice:", e?.error);
        if (e?.error === "not-allowed" || e?.error === "service-not-allowed") {
          return;
        }
      };

      recognition.onend = () => {
        // If TTS is still actively speaking, recreate fresh recognition after debounce
        if (isPlayingInternal && !stopRequested) {
          clearTimeout(interruptRestartTimer);
          interruptRestartTimer = setTimeout(() => {
            launchRecognition();
          }, 120);
        }
      };

      recognition.start();
      activeInterruptRecognition = recognition;
    } catch (err) {
      console.debug("Interrupt recognition start notice:", err);
      if (isPlayingInternal && !stopRequested) {
        clearTimeout(interruptRestartTimer);
        interruptRestartTimer = setTimeout(() => {
          launchRecognition();
        }, 200);
      }
    }
  }

  // Small delay to allow previous audio recording tracks to release cleanly
  clearTimeout(interruptRestartTimer);
  interruptRestartTimer = setTimeout(() => {
    launchRecognition();
  }, 100);
}

export function stopInterruptListener(): void {
  if (interruptRestartTimer) {
    clearTimeout(interruptRestartTimer);
    interruptRestartTimer = null;
  }

  if (activeKeydownListener && typeof window !== "undefined") {
    window.removeEventListener("keydown", activeKeydownListener);
    activeKeydownListener = null;
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
