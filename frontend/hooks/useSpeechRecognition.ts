"use client";

import type { MutableRefObject } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

const DISPLAY_MAX_WORDS = 15;
const RESTART_MS = 120;

function lastNWords(text: string, n: number): string {
  const w = text.trim().split(/\s+/).filter(Boolean);
  if (w.length <= n) return w.join(" ");
  return w.slice(-n).join(" ");
}

type SpeechRec = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onresult: ((ev: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((ev: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type SpeechRecognitionResultEvent = {
  resultIndex: number;
  results: SpeechRecognitionResultList;
};

type SpeechRecognitionErrorEvent = {
  error: string;
};

type SpeechRecognitionResultList = {
  length: number;
  item: (i: number) => SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
};

type SpeechRecognitionResult = {
  isFinal: boolean;
  length: number;
  item: (i: number) => SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
};

type SpeechRecognitionAlternative = {
  transcript: string;
};

function getSpeechRecognitionCtor(): (new () => SpeechRec) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRec;
    webkitSpeechRecognition?: new () => SpeechRec;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export interface UseSpeechRecognitionResult {
  isListening: boolean;
  finalTranscript: string;
  interimTranscript: string;
  error: string | null;
  isSupported: boolean;
  /** Synchronously updated full final text (for submit right after stop). */
  finalTextRef: MutableRefObject<string>;
  startListening: () => void;
  stopListening: () => void;
  resetTranscript: () => void;
}

export function useSpeechRecognition(): UseSpeechRecognitionResult {
  const [isListening, setIsListening] = useState(false);
  const [finalTranscript, setFinalTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRec | null>(null);
  const wantListenRef = useRef(false);
  const restartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finalTextRef = useRef("");

  const clearRestartTimer = useCallback(() => {
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
  }, []);

  const resetTranscript = useCallback(() => {
    finalTextRef.current = "";
    setFinalTranscript("");
    setInterimTranscript("");
  }, []);

  const attachRecognition = useCallback(() => {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) return null;
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = true;
    r.lang = "uz-UZ";
    r.maxAlternatives = 1;

    r.onresult = (ev: SpeechRecognitionResultEvent) => {
      let interim = "";
      let finals = "";

      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const res = ev.results[i];
        const alt = res[0];
        const t = (alt?.transcript ?? "").trim();
        if (!t) continue;
        if (res.isFinal) {
          finals += (finals ? " " : "") + t;
        } else {
          interim += (interim ? " " : "") + t;
        }
      }

      if (finals) {
        setFinalTranscript((prev) => {
          const next = (prev ? `${prev} ${finals}` : finals).trim();
          finalTextRef.current = next;
          return next;
        });
      }
      setInterimTranscript(lastNWords(interim, DISPLAY_MAX_WORDS));
    };

    r.onerror = (ev: SpeechRecognitionErrorEvent) => {
      const code = ev.error || "";
      if (code === "no-speech" || code === "audio-capture") return;
      if (code === "aborted") return;
      if (code === "not-allowed" || code === "service-not-allowed") {
        setError(
          "Mikrofon ruxsati berilmadi yoki brauzer bloklayapti. Qulflash belgisidan ruxsat bering; http:// sahifada HTTPS talab qilinishi mumkin.",
        );
        return;
      }
      setError(code || "recognition-error");
    };

    r.onend = () => {
      if (!wantListenRef.current) return;
      clearRestartTimer();
      restartTimerRef.current = setTimeout(() => {
        restartTimerRef.current = null;
        if (!wantListenRef.current) return;
        try {
          recognitionRef.current?.start();
        } catch {
          /* already started */
        }
      }, RESTART_MS);
    };

    recognitionRef.current = r;
    return r;
  }, [clearRestartTimer]);

  const startListening = useCallback(() => {
    setError(null);
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      setError("not-supported");
      return;
    }
    clearRestartTimer();
    wantListenRef.current = true;
    resetTranscript();
    try {
      recognitionRef.current?.abort();
    } catch {
      /* ignore */
    }
    recognitionRef.current = null;
    const r = attachRecognition();
    if (!r) {
      wantListenRef.current = false;
      setError("not-supported");
      return;
    }
    try {
      r.start();
      setIsListening(true);
    } catch (e) {
      wantListenRef.current = false;
      setError(e instanceof Error ? e.message : "start-failed");
    }
  }, [attachRecognition, clearRestartTimer, resetTranscript]);

  const stopListening = useCallback(() => {
    wantListenRef.current = false;
    clearRestartTimer();
    setIsListening(false);
    setInterimTranscript("");
    try {
      recognitionRef.current?.stop();
    } catch {
      /* ignore */
    }
  }, [clearRestartTimer]);

  useEffect(() => {
    return () => {
      wantListenRef.current = false;
      clearRestartTimer();
      try {
        recognitionRef.current?.abort();
      } catch {
        /* ignore */
      }
      recognitionRef.current = null;
    };
  }, [clearRestartTimer]);

  const supported = getSpeechRecognitionCtor() !== null;

  return {
    isListening,
    finalTranscript,
    interimTranscript,
    error,
    isSupported: supported,
    finalTextRef,
    startListening,
    stopListening,
    resetTranscript,
  };
}
