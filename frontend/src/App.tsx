import React, { useState, useEffect } from 'react';
import { ChaiCover } from './components/chai-cover';
import { ChatWorkspace } from './components/chat-workspace';
import { AuthForm } from './components/auth-form';
import { AssistantSpeech } from './components/assistant-speech';
import { ScreenEdgeIllumination } from './components/screen-edge-illumination';
import { useSession, type UserSession } from './lib/auth-client';
import { handleSupabaseRedirectSession, subscribeToSupabaseAuth } from './lib/supabase';

// Autonomous Alexa & Siri style global wake word detection across English, Hindi, Kannada, Sanskrit
const WAKE_PATTERNS = [
  // English: "hey chai", "hi chai", "hello chai", "ok chai", "okay chai", "chai", "wake up chai", and speech-to-text phonetic variations
  /(?:^|\b)(?:hey|hi|hello|ok|okay|hay|hai|a|wake\s+up)\s+(?:chai|chye|chaye|shy|child|try|guy|joy|jai|chain|shine|chi|chay|tai)\b[\s,:]*/i,
  // Hindi / Devanagari: "हे चाय", "हाय चाय", "नमस्ते चाय", "सुनो चाय", "चाई"
  /(?:^|\b)(?:हे|हाय|नमस्ते|सुनो)\s*(?:चाय|चाई)[\s,:]*/i,
  // Kannada: "ಹೇ ಚಾಯ್", "ಹಾಯ್ ಚಾಯ್", "ನಮಸ್ಕಾರ ಚಾಯ್", "ಕೇಳು ಚಾಯ್", "ಚಾಯ್"
  /(?:^|\b)(?:ಹೇ|ಹಾಯ್|ನಮಸ್ಕಾರ|ಕೇಳು)\s*ಚಾಯ್[\s,:]*/i,
  // Sanskrit: "नमस्कारम् चाय", "हे चाय"
  /(?:^|\b)(?:नमस्कारम्)\s*(?:ಚಾಯ್|चाय)[\s,:]*/i,
  // Direct invocation
  /(?:^|\b)(?:chai|chye|chaye|jai)\b[\s,:]*/i,
  /(?:^|\b)(?:चाय|चाई)[\s,:]*/i,
  /(?:^|\b)ಚಾಯ್[\s,:]*/i,
];

function parseWakeWord(transcript: string): { matched: boolean; query: string } {
  const trimmed = transcript.trim();
  for (const pat of WAKE_PATTERNS) {
    const match = trimmed.match(pat);
    if (match && match.index !== undefined) {
      const matchEnd = match.index + match[0].length;
      const query = trimmed.slice(matchEnd).replace(/^[\s,:.!?\-]+/, '').trim();
      return { matched: true, query };
    }
  }
  return { matched: false, query: '' };
}

export default function App() {
  const [currentPath, setCurrentPath] = useState<string>(() => {
    return typeof window !== 'undefined' ? window.location.pathname || '/' : '/';
  });

  const { data: sessionData } = useSession();
  const [currentUser, setCurrentUser] = useState<UserSession | null>(sessionData?.user || null);

  // Global Omnipresent Voice Assistant States
  const [isSpeechAssistantOpen, setIsSpeechAssistantOpen] = useState(false);
  const [speechAssistantInitialPrompt, setSpeechAssistantInitialPrompt] = useState('');
  const [isWakeWordIlluminated, setIsWakeWordIlluminated] = useState(false);

  // Global Alexa-style Wake Word Listener active from ANYWHERE across the app
  useEffect(() => {
    if (typeof window === 'undefined' || isSpeechAssistantOpen) return;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    let recognition: any = null;
    let active = true;
    let restartTimer: any = null;

    function scheduleRestart(delay = 300) {
      if (restartTimer) clearTimeout(restartTimer);
      restartTimer = setTimeout(() => {
        restartTimer = null;
        if (active && !isSpeechAssistantOpen) {
          startWakeWordListener();
        }
      }, delay);
    }

    function startWakeWordListener() {
      if (!active || isSpeechAssistantOpen) return;

      try {
        if (recognition) {
          try {
            recognition.abort();
          } catch {}
          recognition = null;
        }

        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        // en-IN supports multilingual wake words with high sensitivity
        recognition.lang = 'en-IN';

        recognition.onresult = (event: any) => {
          if (!active || isSpeechAssistantOpen) return;

          for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            const { matched, query } = parseWakeWord(transcript);
            if (matched) {
              console.log('[Alexa-Global] 🎙️ Wake word detected anywhere in app:', transcript, '-> Query:', query);
              setIsWakeWordIlluminated(true);
              setSpeechAssistantInitialPrompt(query);
              setIsSpeechAssistantOpen(true);
              setTimeout(() => setIsWakeWordIlluminated(false), 2500);
              try {
                recognition.abort();
              } catch {}
              break;
            }
          }
        };

        recognition.onerror = (e: any) => {
          if (active && !isSpeechAssistantOpen && e.error !== 'not-allowed') {
            scheduleRestart(400);
          }
        };

        recognition.onend = () => {
          if (active && !isSpeechAssistantOpen) {
            scheduleRestart(250);
          }
        };

        recognition.start();
      } catch {
        if (active && !isSpeechAssistantOpen) {
          scheduleRestart(800);
        }
      }
    }

    startWakeWordListener();

    // User gesture warmup to satisfy browser autoplay and microphone sandbox rules
    const handleGestureWarmup = () => {
      if (active && !isSpeechAssistantOpen) {
        try {
          if (window.speechSynthesis) {
            window.speechSynthesis.getVoices();
            if (window.speechSynthesis.paused) window.speechSynthesis.resume();
          }
          if (navigator.mediaDevices?.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
              stream.getTracks().forEach((t) => t.stop());
              startWakeWordListener();
            }).catch(() => {});
          }
        } catch {}
      }
    };

    window.addEventListener('pointerdown', handleGestureWarmup, { once: true, passive: true });
    window.addEventListener('keydown', handleGestureWarmup, { once: true, passive: true });

    // Global custom event to open voice assistant on demand
    const handleOpenVoice = (e: Event) => {
      const custom = e as CustomEvent<string>;
      setIsWakeWordIlluminated(true);
      setSpeechAssistantInitialPrompt(custom.detail || '');
      setIsSpeechAssistantOpen(true);
      setTimeout(() => setIsWakeWordIlluminated(false), 2000);
    };

    window.addEventListener('chai-open-voice', handleOpenVoice);

    return () => {
      active = false;
      if (restartTimer) clearTimeout(restartTimer);
      window.removeEventListener('pointerdown', handleGestureWarmup);
      window.removeEventListener('keydown', handleGestureWarmup);
      window.removeEventListener('chai-open-voice', handleOpenVoice);
      if (recognition) {
        try {
          recognition.abort();
        } catch {}
        recognition = null;
      }
    };
  }, [isSpeechAssistantOpen]);

  useEffect(() => {
    // Detect Supabase OAuth redirect session
    handleSupabaseRedirectSession().then((sbUser) => {
      if (sbUser) {
        localStorage.setItem('chai_auth_user', JSON.stringify(sbUser));
        setCurrentUser(sbUser);
        if (window.location.hash.includes('access_token')) {
          window.history.replaceState({}, '', window.location.pathname);
        }
      }
    });

    // Real-time listener for OAuth logins
    const unsubscribe = subscribeToSupabaseAuth((sbUser) => {
      if (sbUser) {
        localStorage.setItem('chai_auth_user', JSON.stringify(sbUser));
        setCurrentUser(sbUser);
      }
    });

    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (sessionData?.user) {
      setCurrentUser(sessionData.user);
    }
  }, [sessionData]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const getTheme = () => localStorage.getItem('chai-theme') || 'dark';
    const applyTheme = (theme: string) => {
      const root = document.documentElement;
      const isDark = theme !== 'light';
      root.classList.toggle('dark', isDark);
      root.classList.toggle('light', !isDark);
    };

    applyTheme(getTheme());

    // Initialize accent color
    const savedAccent = localStorage.getItem('chai-accent') || 'violet';
    const accentSwatches: Record<string, string> = {
      violet: '#7064e8',
      blue: '#3979df',
      teal: '#148b7e',
      rose: '#ce5478',
      amber: '#c86d1a',
    };
    document.documentElement.style.setProperty(
      '--profile-accent-color',
      accentSwatches[savedAccent] || '#7064e8'
    );

    const handleThemeChange = (e: Event) => {
      const custom = e as CustomEvent<string>;
      applyTheme(custom.detail || getTheme());
    };

    window.addEventListener('chai-theme-change', handleThemeChange);
    return () => window.removeEventListener('chai-theme-change', handleThemeChange);
  }, []);

  useEffect(() => {
    const handleNav = (e: Event) => {
      const custom = e as CustomEvent<string>;
      const nextPath = custom.detail || window.location.pathname || '/';
      setCurrentPath(nextPath);
    };

    const handleAuthChange = (e: Event) => {
      const custom = e as CustomEvent<UserSession | null>;
      setCurrentUser(custom.detail || null);
      if (!custom.detail) {
        // Logged out -> go to cover page
        window.history.pushState({}, '', '/');
        setCurrentPath('/');
      }
    };

    window.addEventListener('chai-navigate', handleNav);
    window.addEventListener('popstate', handleNav);
    window.addEventListener('chai-auth-change', handleAuthChange);

    return () => {
      window.removeEventListener('chai-navigate', handleNav);
      window.removeEventListener('popstate', handleNav);
      window.removeEventListener('chai-auth-change', handleAuthChange);
    };
  }, []);

  const navigateTo = (path: string) => {
    window.history.pushState({}, '', path);
    setCurrentPath(path);
    window.dispatchEvent(new CustomEvent('chai-navigate', { detail: path }));
  };

  const renderCurrentPage = () => {
    // Dedicated Route: /sign-in
    if (currentPath === '/sign-in' || currentPath === '/login') {
      return (
        <main className="min-h-screen flex items-center justify-center p-4 bg-background">
          <AuthForm
            mode="sign-in"
            variant="page"
            onBack={() => navigateTo('/')}
            onModeChange={(mode) => navigateTo(mode === 'sign-up' ? '/sign-up' : '/sign-in')}
          />
        </main>
      );
    }

    // Dedicated Route: /sign-up
    if (currentPath === '/sign-up' || currentPath === '/register') {
      return (
        <main className="min-h-screen flex items-center justify-center p-4 bg-background">
          <AuthForm
            mode="sign-up"
            variant="page"
            onBack={() => navigateTo('/')}
            onModeChange={(mode) => navigateTo(mode === 'sign-up' ? '/sign-up' : '/sign-in')}
          />
        </main>
      );
    }

    // Dedicated Route: /speech, /assistant, or /assistant-speech
    if (
      currentPath === '/speech' ||
      currentPath === '/assistant' ||
      currentPath === '/assistant-speech' ||
      currentPath === '/voice'
    ) {
      return (
        <main className="min-h-screen bg-[#030408]">
          <AssistantSpeech onBack={() => navigateTo(currentUser ? '/workspace' : '/guest')} />
        </main>
      );
    }

    // Workspace Route: /workspace or /guest
    if (currentPath.includes('workspace') || currentPath.includes('guest')) {
      const activeUser = currentUser || (currentPath.includes('guest') ? {
        id: 'guest_session',
        name: 'Guest Operator',
        email: 'guest@chai.ai',
        provider: 'guest' as const,
      } : null);

      return (
        <div className="min-h-screen bg-background text-foreground">
          <ChatWorkspace user={activeUser} />
        </div>
      );
    }

    // Root / Cover Landing Page
    return (
      <div className="min-h-screen bg-background text-foreground">
        <ChaiCover />
      </div>
    );
  };

  return (
    <>
      {/* Screen edge illumination when Hey CHAI is detected anywhere */}
      <ScreenEdgeIllumination active={isWakeWordIlluminated} />

      {/* Main Page Layout */}
      {renderCurrentPage()}

      {/* Omnipresent Voice Assistant Modal triggered anywhere */}
      {isSpeechAssistantOpen && (
        <div className="fixed inset-0 z-50 animate-in fade-in zoom-in-95 duration-300">
          <AssistantSpeech
            initialPrompt={speechAssistantInitialPrompt}
            onBack={() => {
              setIsSpeechAssistantOpen(false);
              setSpeechAssistantInitialPrompt('');
            }}
          />
        </div>
      )}
    </>
  );
}
