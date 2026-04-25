export type ServerJsonMessage =
  | { type: "status"; stage: string; detail: string }
  | { type: "transcript"; text: string; final: boolean }
  | { type: "reply_text"; text: string }
  | { type: "audio_meta"; sampleRate: number; encoding: string }
  | { type: "pong" }
  | { type: "error"; code: string; message: string };

function withWsToken(url: string): string {
  const tok = process.env.NEXT_PUBLIC_WS_API_KEY?.trim();
  if (!tok) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(tok)}`;
}

export function defaultWsUrl(): string {
  if (typeof window === "undefined") {
    return withWsToken("ws://127.0.0.1:8000/ws/voice");
  }
  const env = process.env.NEXT_PUBLIC_WS_URL?.trim();
  const base =
    env ||
    (() => {
      const { protocol, hostname } = window.location;
      const wsProto = protocol === "https:" ? "wss:" : "ws:";
      return `${wsProto}//${hostname}:8000/ws/voice`;
    })();
  return withWsToken(base);
}

export interface VoiceWsHandlers {
  onJson: (msg: ServerJsonMessage) => void;
  onBinary: (buf: ArrayBuffer) => void;
  onOpen: () => void;
  onClose: () => void;
  onError: (e: Event) => void;
}

export function connectVoiceSocket(
  url: string,
  handlers: VoiceWsHandlers,
): WebSocket {
  const ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => handlers.onOpen();
  ws.onclose = () => handlers.onClose();
  ws.onerror = (e) => handlers.onError(e);
  ws.onmessage = (ev) => {
    if (typeof ev.data === "string") {
      try {
        const msg = JSON.parse(ev.data) as ServerJsonMessage;
        handlers.onJson(msg);
      } catch {
        /* ignore */
      }
    } else if (ev.data instanceof ArrayBuffer) {
      handlers.onBinary(ev.data);
    }
  };
  return ws;
}
