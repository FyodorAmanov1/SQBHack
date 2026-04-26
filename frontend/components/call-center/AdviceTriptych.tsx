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
      <div className="mb-3 flex shrink-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-zinc-200 pb-2 dark:border-zinc-700">
        <h2 className="text-base font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
          2. AI yordam
        </h2>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Yangilangan: {formatTime(updatedAt)}
        </p>
      </div>
      {error && (
        <p className="mb-2 shrink-0 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950/50 dark:text-red-200">
          {error}
        </p>
      )}
      {loading && (
        <p className="mb-2 text-sm text-zinc-500 dark:text-zinc-400">Maslahat hisoblanmoqda…</p>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <ul className="grid list-none grid-cols-1 content-start items-stretch gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {list.map((p, i) => (
            <li
              key={`${p.title}-${i}`}
              className="flex min-h-0 min-w-0 flex-col rounded-2xl border border-amber-300/90 bg-amber-50 p-4 shadow-sm dark:border-amber-600/50 dark:bg-zinc-800/95"
            >
              <h3 className="shrink-0 text-sm font-semibold text-amber-950 dark:text-amber-300">
                {p.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-amber-950 dark:text-zinc-100">
                {p.content}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
