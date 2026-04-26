"use client";

import type { AdvicePanel } from "@/lib/clientAnalytics";

const PLACEHOLDERS: AdvicePanel[] = [
  {
    title: "Darhol qilish",
    content: "Maslahat olish uchun yuqorida «Maslahatni yangilash» tugmasini bosing.",
  },
  {
    title: "Mijoz bilan muloqot",
    content: "Eshitishni yoqing, transkript to‘plang, keyin maslahatni yangilang.",
  },
  {
    title: "Xavf va ruxsat",
    content: "Identifikatsiya va xavfsizlik bo‘yicha tavsiyalar shu yerga chiqadi.",
  },
];

type Props = {
  panels: AdvicePanel[] | null;
  loading: boolean;
  error: string | null;
  updatedAt: number | null;
};

function formatTime(ms: number | null): string {
  if (ms == null) return "—";
  try {
    return new Date(ms).toLocaleString("uz-UZ");
  } catch {
    return "—";
  }
}

export function AdviceTriptych({ panels, loading, error, updatedAt }: Props) {
  const list =
    panels && panels.length === 3
      ? panels
      : PLACEHOLDERS;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
        <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100">2. AI yordam</h2>
        <p className="text-xs text-zinc-500">Yangilangan: {formatTime(updatedAt)}</p>
      </div>
      {error && (
        <p className="mb-2 shrink-0 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950/50 dark:text-red-200">
          {error}
        </p>
      )}
      {loading && (
        <p className="mb-2 text-sm text-zinc-500">Maslahat hisoblanmoqda…</p>
      )}
      <div className="grid min-h-0 flex-1 grid-rows-3 gap-3 overflow-hidden">
        {list.map((p, i) => (
          <div
            key={`${p.title}-${i}`}
            className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-amber-200/80 bg-amber-50/90 p-4 dark:border-amber-900/50 dark:bg-amber-950/30"
          >
            <h3 className="shrink-0 text-sm font-semibold text-amber-900 dark:text-amber-100">
              {p.title}
            </h3>
            <p className="mt-2 min-h-0 flex-1 overflow-y-auto text-sm leading-relaxed text-amber-950/90 dark:text-amber-50/90">
              {p.content}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
