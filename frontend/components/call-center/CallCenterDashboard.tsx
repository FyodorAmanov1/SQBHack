"use client";

import Image from "next/image";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { Group, Panel, Separator, useDefaultLayout } from "react-resizable-panels";
import { apiFetch } from "@/lib/apiBase";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import type {
  AdvicePanel,
  ClientAnalytics,
  OperatorAdviceResponse,
} from "@/lib/clientAnalytics";
import { AdviceTriptych } from "./AdviceTriptych";
import { CallCenterListener } from "./CallCenterListener";
import { ClientContextPanel } from "./ClientContextPanel";

const DEFAULT_CLIENT_ID = "AD0135673";

const noopLayoutStorage: Pick<Storage, "getItem" | "setItem"> = {
  getItem: () => null,
  setItem: () => {},
};

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
  const u = o.updatedAt ?? o.updated_at_epoch_ms;
  const updated = typeof u === "number" ? u : Date.now();
  return { panels, updatedAt: updated };
}

export function CallCenterDashboard() {
  const isDesktop = useMediaQuery("(min-width: 1024px)");
  /** true only after client mount: avoids Panel SSR/CSR style mismatch in react-resizable-panels. */
  const [resizableActive, setResizableActive] = useState(false);
  useLayoutEffect(() => {
    setResizableActive(true);
  }, []);
  /** v2: v4 treats numeric panel sizes as px (not %); old localStorage may also store bad splits. */
  const layoutKey = isDesktop ? "callcenter-h-v2" : "callcenter-v-v2";
  const { defaultLayout, onLayoutChanged } = useDefaultLayout({
    id: resizableActive ? layoutKey : "callcenter-pending",
    panelIds: ["client", "work"],
    storage: resizableActive && typeof window !== "undefined" ? window.localStorage : noopLayoutStorage,
  });
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

  const clientPanelSectionClassName =
    "h-full min-h-0 min-w-0 overflow-y-auto border-b border-zinc-200 bg-zinc-50/50 p-4 dark:border-zinc-700/60 dark:bg-zinc-950/50 lg:border-b-0 lg:border-r";

  /** CSS-only 2 col before resizable-panels hydrates; Panel does not get these. */
  const clientStaticSectionClassName = `${clientPanelSectionClassName} flex-1 min-w-0 lg:min-w-[22%] lg:max-w-[55%] lg:w-[35%] lg:shrink-0`;

  const clientPanelSection = (
    <section className={clientPanelSectionClassName} aria-label="Mijoz">
      <ClientContextPanel
        data={clientData}
        loading={clientLoading}
        error={clientError}
      />
    </section>
  );

  const clientStaticSection = (
    <section className={clientStaticSectionClassName} aria-label="Mijoz">
      <ClientContextPanel
        data={clientData}
        loading={clientLoading}
        error={clientError}
      />
    </section>
  );

  const workColumn = (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col bg-white dark:bg-zinc-900">
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden border-b border-zinc-200 p-5 dark:border-zinc-700/60">
        <AdviceTriptych
          panels={advice?.panels ?? null}
          loading={adviceLoading}
          error={adviceError}
          updatedAt={advice?.updatedAt ?? null}
        />
      </div>
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <CallCenterListener onTranscriptChange={setTranscript} />
      </div>
    </div>
  );

  const staticMainLayout = (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      {clientStaticSection}
      <div
        className="h-1.5 shrink-0 bg-zinc-200/60 dark:bg-zinc-700/50 lg:hidden"
        aria-hidden
      />
      <div
        className="hidden w-1.5 shrink-0 bg-zinc-200/60 dark:bg-zinc-700/50 lg:block"
        aria-hidden
      />
      {workColumn}
    </div>
  );

  const resizableMainLayout = (
    <Group
      key={layoutKey}
      id={layoutKey}
      orientation={isDesktop ? "horizontal" : "vertical"}
      className="h-full min-h-0"
      defaultLayout={defaultLayout}
      onLayoutChanged={onLayoutChanged}
    >
      <Panel
        id="client"
        defaultSize={isDesktop ? "35%" : "42%"}
        minSize={isDesktop ? "22%" : "28%"}
        maxSize={isDesktop ? "55%" : "60%"}
        className="min-h-0 min-w-0"
      >
        {clientPanelSection}
      </Panel>
      <Separator
        className={
          isDesktop
            ? "w-1.5 shrink-0 cursor-col-resize bg-zinc-200/60 transition-colors hover:bg-amber-400/25 focus:outline-none focus:ring-2 focus:ring-amber-500/40 dark:bg-zinc-700/50 dark:hover:bg-amber-500/20"
            : "h-1.5 w-full min-h-1.5 shrink-0 cursor-row-resize bg-zinc-200/60 transition-colors hover:bg-amber-400/25 focus:outline-none focus:ring-2 focus:ring-amber-500/40 dark:bg-zinc-700/50 dark:hover:bg-amber-500/20"
        }
        aria-label="Kenglikni o‘zgartirish"
      />
      <Panel
        id="work"
        defaultSize={isDesktop ? "65%" : "58%"}
        minSize={isDesktop ? "30%" : "25%"}
        className="min-h-0 min-w-0"
      >
        {workColumn}
      </Panel>
    </Group>
  );

  const mainPanels = resizableActive ? resizableMainLayout : staticMainLayout;

  return (
    <main className="flex h-[100dvh] flex-col overflow-hidden bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="shrink-0 border-b border-zinc-200 px-4 py-3.5 dark:border-zinc-700/60">
        <div className="flex items-center gap-4">
          <div className="relative h-14 w-40 shrink-0 sm:h-16 sm:w-44">
            <Image
              src="/brand/aytingchi.png"
              alt="Aytingchi"
              fill
              className="object-contain object-left"
              sizes="(max-width: 640px) 160px, 180px"
              priority
            />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-bold sm:text-lg">Call-markaz yordamchisi</h1>
            <p className="text-xs text-zinc-500">
              1) Mijoz ID ni kiriting → 2) Eshitish → 3) «Maslahatni yangilash»
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <label className="text-xs text-zinc-500" htmlFor="client-id">
                Mijoz ID
              </label>
              <input
                id="client-id"
                value={clientId}
                onChange={(e) =>
                  setClientId(e.target.value.trim() || DEFAULT_CLIENT_ID)
                }
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
          </div>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-hidden">{mainPanels}</div>
    </main>
  );
}
