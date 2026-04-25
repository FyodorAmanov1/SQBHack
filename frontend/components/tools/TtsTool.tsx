"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/apiBase";

type VoiceEntry = { id: string; label: string; filename: string };

export function TtsTool() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voices, setVoices] = useState<VoiceEntry[]>([]);
  const [speakerId, setSpeakerId] = useState<string | null>(null);
  /** Object URL for last successful TTS; revoked only when replaced or unmount. */
  const [savedAudioUrl, setSavedAudioUrl] = useState<string | null>(null);
  const [lastInputText, setLastInputText] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const savedUrlRef = useRef<string | null>(null);

  useEffect(() => {
    savedUrlRef.current = savedAudioUrl;
  }, [savedAudioUrl]);

  useEffect(() => {
    return () => {
      if (savedUrlRef.current) {
        URL.revokeObjectURL(savedUrlRef.current);
        savedUrlRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await apiFetch("/voices?refresh=1");
        if (!r.ok || cancelled) return;
        const j = (await r.json()) as {
          voices?: VoiceEntry[];
          defaultSpeakerId?: string | null;
        };
        if (cancelled) return;
        setVoices(Array.isArray(j.voices) ? j.voices : []);
        const d = j.defaultSpeakerId;
        if (typeof d === "string" && d.length > 0) setSpeakerId(d);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const generate = async () => {
    const t = text.trim();
    if (!t) {
      setError("Matn kiriting.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await apiFetch("/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: t,
          ...(speakerId ? { speakerId } : {}),
        }),
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const j = (await res.json()) as { detail?: unknown };
          if (typeof j.detail === "string") detail = j.detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setSavedAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
      setLastInputText(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : "TTS muvaffaqiyatsiz.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-8">
      {voices.length > 0 && (
        <div>
          <label
            htmlFor="tts-speaker"
            className="block text-sm font-medium text-zinc-800 dark:text-zinc-200"
          >
            Ovoz namunasi (myVoice)
          </label>
          <select
            id="tts-speaker"
            value={speakerId ?? ""}
            onChange={(e) =>
              setSpeakerId(e.target.value === "" ? null : e.target.value)
            }
            disabled={loading}
            className="mt-2 w-full max-w-md rounded-xl border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
          >
            <option value="">Standart (.env)</option>
            {voices.map((v) => (
              <option key={v.id} value={v.id} title={v.id}>
                {v.label} ({v.filename})
              </option>
            ))}
          </select>
        </div>
      )}

      <div>
        <label
          htmlFor="tts-text"
          className="block text-sm font-medium text-zinc-800 dark:text-zinc-200"
        >
          O‘qiladigan matn
        </label>
        <textarea
          id="tts-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          placeholder="Masalan: Bugun havo juda yaxshi."
          className="mt-2 w-full rounded-xl border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
          disabled={loading}
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void generate()}
          disabled={loading || !text.trim()}
          className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {loading ? "Tayyorlanmoqda…" : "Tinglash"}
        </button>
        {savedAudioUrl && (
          <a
            href={savedAudioUrl}
            download="realtimevoice-tts.wav"
            className="rounded-xl border border-zinc-300 px-4 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            Yuklab olish
          </a>
        )}
      </div>
      {savedAudioUrl && (
        <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900/80">
          <p className="mb-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
            Oxirgi ovoz (yangi «Tinglash» bosilguncha saqlanadi)
          </p>
          {lastInputText && (
            <p className="mb-3 line-clamp-2 text-xs text-zinc-600 dark:text-zinc-300">
              Matn: {lastInputText}
            </p>
          )}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              aria-label="Ijro etish"
              onClick={() => {
                const el = audioRef.current;
                if (!el) return;
                void el.play();
              }}
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700"
            >
              <span className="text-base leading-none" aria-hidden>
                ▶
              </span>
              Ijro etish
            </button>
            <button
              type="button"
              onClick={() => audioRef.current?.pause()}
              className="rounded-xl border border-zinc-300 px-4 py-2.5 text-sm font-medium text-zinc-800 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-100 dark:hover:bg-zinc-800"
            >
              To‘xtatish
            </button>
          </div>
          <audio
            ref={audioRef}
            src={savedAudioUrl}
            controls
            className="h-10 w-full max-w-md"
            preload="auto"
          />
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            Pastdagi slayder orqali vaqt bo‘yicha siljishingiz mumkin.
          </p>
        </div>
      )}
      {error && (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900 dark:border-rose-900/50 dark:bg-rose-950/50 dark:text-rose-100">
          {error}
        </p>
      )}
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Yangi matn bilan «Tinglash»ni bossangiz, avvalgi ovoz almashtiriladi.
      </p>
    </div>
  );
}
