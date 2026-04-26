"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";

const MSG_HTTPS_NEEDED =
  "Ovozni eshitish uchun HTTPS kerak: brauzer mikrofoni odatda http:// da bloklaydi.";

const MSG_MIC_DENIED =
  "Mikrofonga ruxsat bermagansiz. Manzil qatoridagi qulflash belgisidan ruxsat bering.";

type Props = {
  /** Full transcript: final segments joined (for advice + display). */
  onTranscriptChange: (text: string) => void;
};

export function CallCenterListener({ onTranscriptChange }: Props) {
  /** False on server + first paint — avoids hydration mismatch (Speech API / secure context). */
  const [envReady, setEnvReady] = useState(false);
  const [insecure, setInsecure] = useState(false);
  const {
    isListening,
    finalTranscript,
    interimTranscript,
    error: speechError,
    isSupported: speechSupported,
    finalTextRef,
    startListening: startSpeechListening,
    stopListening: stopSpeechListening,
    resetTranscript: resetSpeechTranscript,
  } = useSpeechRecognition();

  const prevFinalRef = useRef("");

  useEffect(() => {
    setInsecure(!window.isSecureContext);
    setEnvReady(true);
  }, []);

  useEffect(() => {
    if (finalTranscript === prevFinalRef.current) return;
    prevFinalRef.current = finalTranscript;
    onTranscriptChange(finalTranscript);
  }, [finalTranscript, onTranscriptChange]);

  const displayLine = [finalTranscript, interimTranscript]
    .filter(Boolean)
    .join(" ")
    .trim();

  useEffect(() => {
    if (!speechError) return;
    if (speechError === "not-supported") return;
    if (speechError === "not-allowed" || speechError === "service-not-allowed") {
      window.alert(MSG_MIC_DENIED);
    }
  }, [speechError]);

  const onToggle = useCallback(() => {
    if (insecure) {
      window.alert(MSG_HTTPS_NEEDED);
      return;
    }
    if (!speechSupported) {
      window.alert("Brauzeringizda nutqni tanib olish (Web Speech API) qo‘llab-quvvatlanmaydi.");
      return;
    }
    if (isListening) {
      stopSpeechListening();
    } else {
      void startSpeechListening();
    }
  }, [
    insecure,
    isListening,
    speechSupported,
    startSpeechListening,
    stopSpeechListening,
  ]);

  const onClear = useCallback(() => {
    resetSpeechTranscript();
    prevFinalRef.current = "";
    onTranscriptChange("");
    // sync ref used by useSpeechRecognition for immediate submit
    finalTextRef.current = "";
  }, [finalTextRef, onTranscriptChange, resetSpeechTranscript]);

  return (
    <div className="flex h-full min-h-0 flex-col p-4">
      <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100">3. Suhbat</h2>
      <p className="mt-1 text-xs text-zinc-500">
        Nutq bu joyda matnga aylantiriladi; ovoz yuborilmaydi. Mijoz va operator bitta oqimda
        eshitilishi mumkin.
      </p>

      {envReady && insecure && (
        <p className="mt-3 text-sm text-amber-800 dark:text-amber-200">{MSG_HTTPS_NEEDED}</p>
      )}
      {envReady && !speechSupported && !insecure && (
        <p className="mt-3 text-sm text-amber-800 dark:text-amber-200">
          Nutq API mavjud emas. Chrome yoki Edge sinab ko‘ring.
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onToggle}
          disabled={!envReady || insecure || !speechSupported}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
        >
          {isListening ? "Pauza" : "Eshitishni boshlash"}
        </button>
        <button
          type="button"
          onClick={onClear}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm text-zinc-700 dark:border-zinc-600 dark:text-zinc-300"
        >
          Tozalash
        </button>
      </div>

      <div
        className="mt-4 min-h-0 flex-1 overflow-y-auto rounded-lg border border-zinc-200 bg-zinc-50/80 p-3 text-sm leading-relaxed text-zinc-800 dark:border-zinc-800 dark:bg-zinc-950/50 dark:text-zinc-200"
        aria-live="polite"
      >
        {displayLine ? (
          <span className="whitespace-pre-wrap">{displayLine}</span>
        ) : (
          <span className="text-zinc-400">
            «Eshitishni boshlash»ni bosing, matn shu yerda paydo bo‘ladi.
          </span>
        )}
      </div>
    </div>
  );
}
