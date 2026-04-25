"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/apiBase";
import { UZ_SYSTEM_PROMPT } from "@/lib/uzSystemPrompt";

type Role = "user" | "assistant";

type Msg = { id: string; role: Role; content: string };

function id(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function TextChatTool() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, []);

  useEffect(() => {
    scrollBottom();
  }, [messages, scrollBottom]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setError(null);
    setInput("");
    const userMsg: Msg = { id: id(), role: "user", content: text };
    setMessages((m) => [...m, userMsg]);
    setLoading(true);
    try {
      const historyForApi = [...messages, userMsg].map(({ role, content }) => ({
        role,
        content,
      }));
      const body = {
        messages: [
          { role: "system" as const, content: UZ_SYSTEM_PROMPT },
          ...historyForApi,
        ],
      };
      const res = await apiFetch("/llm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
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
      const data = (await res.json()) as { text: string };
      const reply = (data.text || "").trim();
      setMessages((m) => [
        ...m,
        { id: id(), role: "assistant", content: reply || "(Bo‘sh javob)" },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Xatolik yuz berdi.");
      setMessages((m) => m.filter((x) => x.id !== userMsg.id));
      setInput(text);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-[calc(100dvh-3.25rem)] flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto flex max-w-2xl flex-col gap-3">
          {messages.length === 0 && (
            <p className="rounded-2xl border border-dashed border-zinc-300 bg-white/70 px-4 py-6 text-center text-sm text-zinc-600 dark:border-zinc-600 dark:bg-zinc-900/50 dark:text-zinc-400">
              Savolingizni yozing va <strong>Yuborish</strong>ni bosing. Javoblar
              o‘zbek lotin alifbosida keladi.
            </p>
          )}
          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[min(90%,28rem)] rounded-2xl rounded-br-md bg-zinc-900 px-4 py-2.5 text-[15px] leading-relaxed text-white dark:bg-zinc-700">
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={m.id} className="flex justify-start">
                <div className="max-w-[min(92%,32rem)] rounded-2xl rounded-bl-md border border-zinc-200 bg-white px-4 py-2.5 text-[15px] leading-relaxed text-zinc-800 shadow-sm dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100">
                  {m.content}
                </div>
              </div>
            ),
          )}
        </div>
      </div>
      {error && (
        <div className="shrink-0 border-t border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-900 dark:border-rose-900/50 dark:bg-rose-950/60 dark:text-rose-100">
          {error}
        </div>
      )}
      <div className="shrink-0 border-t border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-2xl gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={2}
            placeholder="Savolingizni yozing…"
            className="min-h-[2.75rem] flex-1 resize-y rounded-xl border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
            disabled={loading}
          />
          <button
            type="button"
            onClick={() => void send()}
            disabled={loading || !input.trim()}
            className="shrink-0 self-end rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? "Kutilmoqda…" : "Yuborish"}
          </button>
        </div>
      </div>
    </div>
  );
}
