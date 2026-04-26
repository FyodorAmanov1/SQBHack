"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/apiBase";

export function SttTool() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const transcribe = async () => {
    if (!file) {
      setError("Avval audio fayl tanlang.");
      return;
    }
    setError(null);
    setLoading(true);
    setResult("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiFetch("/stt", { method: "POST", body: fd });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const j = (await res.json()) as { detail?: unknown };
          if (typeof j.detail === "string") detail = j.detail;
        } catch {
          /* ignore */
        }
        if (res.status === 501) {
          throw new Error(
            `${detail} — call-center asosiy sahifasida brauzer nutq API ishlatiladi; ` +
              "server STT uchun backend .env da STT_ENABLED=true qiling.",
          );
        }
        throw new Error(detail);
      }
      const data = (await res.json()) as { text: string };
      setResult((data.text || "").trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Transkripsiya muvaffaqiyatsiz.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-8">
      <div>
        <label className="block text-sm font-medium text-zinc-800 dark:text-zinc-200">
          Audio fayl
        </label>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          WAV, FLAC, MP3 va boshqa qo‘llab-quvvatlanadigan formatlar.
        </p>
        <input
          type="file"
          accept="audio/*,.wav,.flac,.ogg,.webm,.mp3,.m4a"
          className="mt-2 block w-full text-sm text-zinc-700 file:mr-3 file:rounded-lg file:border-0 file:bg-emerald-600 file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-emerald-700 dark:text-zinc-300"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setFile(f);
            setResult("");
            setError(null);
          }}
        />
      </div>
      <button
        type="button"
        onClick={() => void transcribe()}
        disabled={loading || !file}
        className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        {loading ? "Qayta ishlanmoqda…" : "Transkripsiya qilish"}
      </button>
      {error && (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900 dark:border-rose-900/50 dark:bg-rose-950/50 dark:text-rose-100">
          {error}
        </p>
      )}
      {result && (
        <div>
          <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
            Natija
          </h2>
          <p className="mt-2 whitespace-pre-wrap rounded-xl border border-zinc-200 bg-white p-4 text-sm leading-relaxed text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100">
            {result}
          </p>
        </div>
      )}
    </div>
  );
}
