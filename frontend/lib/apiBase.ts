/**
 * HTTP origin for FastAPI REST (/stt, /llm, /tts).
 * Uses NEXT_PUBLIC_API_URL, else derives from NEXT_PUBLIC_WS_URL origin, else dev fallback.
 */

export function apiOrigin(): string {
  const explicit = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (explicit) {
    return explicit.replace(/\/+$/, "");
  }
  const ws = process.env.NEXT_PUBLIC_WS_URL?.trim();
  if (ws) {
    try {
      const u = new URL(ws);
      u.protocol = u.protocol === "wss:" ? "https:" : "http:";
      return u.origin;
    } catch {
      /* ignore */
    }
  }
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    const scheme = protocol === "https:" ? "https" : "http";
    return `${scheme}://${hostname}:8000`;
  }
  return "http://127.0.0.1:8000";
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const base = apiOrigin();
  const rel = path.startsWith("/") ? path : `/${path}`;
  const url = `${base}${rel}`;
  const headers = new Headers(init?.headers);
  const key = process.env.NEXT_PUBLIC_WS_API_KEY?.trim();
  if (key) {
    headers.set("X-API-Key", key);
  }
  return fetch(url, { ...init, headers });
}
