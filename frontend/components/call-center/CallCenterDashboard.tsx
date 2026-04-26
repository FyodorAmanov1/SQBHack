"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/apiBase";
import type {
  AdvicePanel,
  ClientAnalytics,
  OperatorAdviceResponse,
} from "@/lib/clientAnalytics";
import { AdviceTriptych } from "./AdviceTriptych";
import { CallCenterListener } from "./CallCenterListener";
import { ClientContextPanel } from "./ClientContextPanel";

const DEFAULT_CLIENT_ID = "AD0135673";

function normalizeAdvicePayload(j: unknown): OperatorAdviceResponse | null {
  if (!j || typeof j !== "object") return null;
  const o = j as Record<string, unknown>;
  const rawPanels = o.panels;
  if (!Array.isArray(rawPanels)) return null;
  const panels: AdvicePanel[] = rawPanels
    .map((p) => {
      if (!p || typeof p !== "object") return null;
      const x = p as Record<string, unknown>;
      return {
        title: String(x.title ?? ""),
        content: String(x.content ?? ""),
      };
    })
    .filter((p): p is AdvicePanel => p != null);
  if (panels.length < 1) return null;
  const updated =
    typeof o.updatedAt === "number"
      ? o.updatedAt
      : typeof o.updated_at_epoch_ms === "number"
        ? o.updated_at_epoch_ms
        : Date.now();
  return { panels, updatedAt: updated };
}

export function CallCenterDashboard() {
  const [clientId, setClientId] = useState(DEFAULT_CLIENT_ID);
  const [clientData, setClientData] = useState<ClientAnalytics | null>(null);
  const [clientLoading, setClientLoading] = useState(true);
  const [clientError, setClientError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState("");
  const [advice, setAdvice] = useState<OperatorAdviceResponse | null>(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceError, setAdviceError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setClientLoading(true);
    setClientError(null);
    void (async () => {
      try {
        const r = await apiFetch(
          `/client-analytics/${encodeURIComponent(clientId)}`,
          { method: "GET" },
        );
        if (!r.ok) {
          const t = await r.text();
          if (!cancelled) {
            setClientError(t.slice(0, 200) || `HTTP ${r.status}`);
            setClientData(null);
          }
          return;
        }
        const j = (await r.json()) as ClientAnalytics;
        if (!cancelled) {
          setClientData(j);
          setClientError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setClientError(e instanceof Error ? e.message : "Tarmoq xatoligi");
          setClientData(null);
        }
      } finally {
        if (!cancelled) setClientLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const refreshAdvice = useCallback(async () => {
    setAdviceError(null);
    setAdviceLoading(true);
    try {
      const r = await apiFetch("/operator-advice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: clientId,
          transcript,
          use_server_client_context: true,
        }),
      });
      if (!r.ok) {
        let detail = `HTTP ${r.status}`;
        try {
          const j = (await r.json()) as { detail?: unknown };
          if (typeof j.detail === "string") detail = j.detail;
        } catch {
          const t = await r.text();
          if (t) detail = t.slice(0, 300);
        }
        setAdviceError(detail);
        return;
      }
      const j = await r.json();
      const n = normalizeAdvicePayload(j);
      if (n && n.panels.length >= 3) {
        setAdvice({
          panels: n.panels.slice(0, 3),
          updatedAt: n.updatedAt,
        });
      } else {
        setAdviceError("Javob formati noto‘g‘ri.");
      }
    } catch (e) {
      setAdviceError(e instanceof Error ? e.message : "Maslahat olinmadi");
    } finally {
      setAdviceLoading(false);
    }
  }, [clientId, transcript]);

  return (
    <main className="flex h-[100dvh] flex-col overflow-hidden bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="shrink-0 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h1 className="text-lg font-bold">Call-markaz yordamchisi</h1>
        <p className="text-xs text-zinc-500">
          Mijoz konteksti, AI maslahatlari va suhbat transkripti (brauzer STT)
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label className="text-xs text-zinc-500" htmlFor="client-id">
            Mijoz ID
          </label>
          <input
            id="client-id"
            value={clientId}
            onChange={(e) => setClientId(e.target.value.trim() || DEFAULT_CLIENT_ID)}
            className="w-40 rounded border border-zinc-300 bg-white px-2 py-1 font-mono text-sm dark:border-zinc-600 dark:bg-zinc-900"
            placeholder="AD0135673"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={() => void refreshAdvice()}
            disabled={adviceLoading}
            className="rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            {adviceLoading ? "Kutilmoqda…" : "Maslahatni yangilash"}
          </button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)_minmax(0,1fr)]">
        <section className="min-h-0 overflow-y-auto border-b border-zinc-200 p-4 lg:border-b-0 lg:border-r dark:border-zinc-800">
          <ClientContextPanel
            data={clientData}
            loading={clientLoading}
            error={clientError}
          />
        </section>
        <section className="min-h-0 overflow-hidden border-b border-zinc-200 p-4 lg:border-b-0 lg:border-r dark:border-zinc-800">
          <AdviceTriptych
            panels={advice?.panels ?? null}
            loading={adviceLoading}
            error={adviceError}
            updatedAt={advice?.updatedAt ?? null}
          />
        </section>
        <section className="min-h-0 flex flex-col overflow-hidden bg-white dark:bg-zinc-900">
          <div className="shrink-0 border-b border-zinc-200 px-4 py-2 dark:border-zinc-800">
            <h2 className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
              Eshitish oynasi
            </h2>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            <CallCenterListener onTranscriptChange={setTranscript} />
          </div>
        </section>
      </div>
    </main>
  );
}
