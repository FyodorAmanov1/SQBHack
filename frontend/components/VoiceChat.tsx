"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/apiBase";
import { PcmPlayer } from "@/lib/pcmPlayer";
import {
  loadChatOptions,
  saveChatOptions,
  type ChatOptions,
} from "@/lib/chatOptions";
import {
  connectVoiceSocket,
  defaultWsUrl,
  type ServerJsonMessage,
} from "@/lib/voiceWs";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";

type ConnState = "disconnected" | "connecting" | "connected" | "recording";

type ChatRole = "user" | "assistant";

type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
};

type VoiceEntry = {
  id: string;
  label: string;
  filename: string;
};

const MAX_RECONNECT = 8;
const BASE_DELAY_MS = 800;
// Application-level heartbeat: keeps idle TCP alive across NAT/proxy timeouts
// and lets us detect a dead socket faster than the browser's built-in close.
const HEARTBEAT_INTERVAL_MS = 25_000;
// How long startRecording will wait for the socket to reach OPEN after kicking
// off an immediate reconnect.
const WAIT_FOR_OPEN_MS = 1_500;

/** Brauzer nutq API xatoliklari uchun (masalan, mikrofon bloklangan). */
const MSG_MIC_DENIED =
  "Brauzer mikrofonga ruxsat bermadi. Manzil satridagi qulflash belgisini bosing, «Mikrofon» uchun «Ruxsat berish»ni tanlang, keyin sahifani yangilang.";

const MSG_HTTPS_NEEDED =
  "Ovozli yozuv uchun HTTPS kerak: http:// manzilida brauzer mikrofonni odatda bloklaydi. Serverga TLS qo‘shing (masalan, Caddy) yoki https:// orqali oching.";

function pickRecorderMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  const c = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
  ];
  for (const t of c) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function VoiceChat() {
  const [conn, setConn] = useState<ConnState>("disconnected");
  const [statusLine, setStatusLine] = useState("Ulanmagan.");
  const [pipelineStage, setPipelineStage] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [options, setOptions] = useState<ChatOptions>(() => loadChatOptions());
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [voices, setVoices] = useState<VoiceEntry[]>([]);
  const [voiceBootstrapDone, setVoiceBootstrapDone] = useState(false);
  /** `http://` (IP yoki domen) — mikrofon brauzerda odatda bloklanadi. */
  const [insecureSite, setInsecureSite] = useState(false);

  const {
    finalTranscript,
    interimTranscript,
    error: speechError,
    isSupported: speechSupported,
    finalTextRef,
    startListening: startSpeechListening,
    stopListening: stopSpeechListening,
    resetTranscript: resetSpeechTranscript,
  } = useSpeechRecognition();

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);
  const recordingRef = useRef(false);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Exposed by the WS effect so user actions (mic click) can force an
  // immediate reconnect instead of waiting for the exponential backoff.
  const reconnectNowRef = useRef<() => void>(() => {});

  const playerRef = useRef<PcmPlayer | null>(null);
  const expectingTtsRef = useRef(false);
  // HTMLAudioElement used by the REST fallback (and reused across replies).
  const fallbackAudioRef = useRef<HTMLAudioElement | null>(null);
  const fallbackAudioUrlRef = useRef<string | null>(null);
  // Mirror of the chat history that the REST /voice_reply endpoint needs.
  // We keep only user/assistant pairs, trimmed to the last N turns to bound
  // request size.
  const restHistoryRef = useRef<{ role: ChatRole; content: string }[]>([]);

  /** `media` = MediaRecorder → server /stt; `speech` = brauzer nutq API. */
  const captureModeRef = useRef<"idle" | "media" | "speech">("idle");
  const micStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    saveChatOptions(options);
  }, [options]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await apiFetch("/voices?refresh=1");
        if (!cancelled && r.ok) {
          const j = (await r.json()) as {
            voices?: VoiceEntry[];
            defaultSpeakerId?: string | null;
          };
          setVoices(Array.isArray(j.voices) ? j.voices : []);
          const def = j.defaultSpeakerId;
          setOptions((o) => {
            if (o.speakerId != null) return o;
            if (typeof def === "string" && def.length > 0) {
              return { ...o, speakerId: def };
            }
            return o;
          });
        }
      } catch {
        /* ignore */
      } finally {
        if (!cancelled) setVoiceBootstrapDone(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setInsecureSite(
      typeof window !== "undefined" && !window.isSecureContext,
    );
  }, []);

  useEffect(() => {
    return () => {
      if (fallbackAudioUrlRef.current) {
        URL.revokeObjectURL(fallbackAudioUrlRef.current);
        fallbackAudioUrlRef.current = null;
      }
      if (fallbackAudioRef.current) {
        try {
          fallbackAudioRef.current.pause();
        } catch {
          /* ignore */
        }
        fallbackAudioRef.current.src = "";
        fallbackAudioRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!voiceBootstrapDone) return;
    if (!optionsOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOptionsOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [optionsOpen]);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, []);

  useEffect(() => {
    if (options.autoScroll) scrollToBottom();
  }, [messages, statusLine, scrollToBottom, options.autoScroll]);

  useEffect(() => {
    if (conn !== "recording") return;
    if (captureModeRef.current === "media") {
      setStatusLine("Ovoz yozilmoqda… tugatish uchun yana bosing.");
      return;
    }
    const parts = [finalTranscript, interimTranscript].filter(Boolean);
    if (parts.length === 0) {
      setStatusLine("Tinglanmoqda… gapiring, tugatish uchun to‘xtating.");
      return;
    }
    setStatusLine(parts.join(" "));
  }, [conn, finalTranscript, interimTranscript]);

  useEffect(() => {
    if (!speechError) return;
    if (speechError === "not-supported") {
      setError("Brauzeringiz ovozni matnga (Web Speech API) qo‘llab-quvvatlamaydi.");
      return;
    }
    if (speechError === "not-allowed" || speechError === "service-not-allowed") {
      setError(MSG_MIC_DENIED);
      return;
    }
    setError(speechError);
  }, [speechError]);

  const stopCaptureOnly = useCallback(() => {
    stopSpeechListening();
    recordingRef.current = false;
    captureModeRef.current = "idle";
    try {
      if (
        mediaRecorderRef.current &&
        mediaRecorderRef.current.state !== "inactive"
      ) {
        mediaRecorderRef.current.stop();
      }
    } catch {
      /* ignore */
    }
    mediaRecorderRef.current = null;
    mediaChunksRef.current = [];
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
  }, [stopSpeechListening]);

  const stopPlaybackOnly = useCallback(() => {
    playerRef.current?.close();
    playerRef.current = null;
    expectingTtsRef.current = false;
    if (fallbackAudioRef.current) {
      try {
        fallbackAudioRef.current.pause();
        fallbackAudioRef.current.currentTime = 0;
      } catch {
        /* ignore */
      }
    }
  }, []);

  const cleanupAudio = useCallback(() => {
    stopCaptureOnly();
    stopPlaybackOnly();
  }, [stopCaptureOnly, stopPlaybackOnly]);

  useEffect(() => {
    intentionalCloseRef.current = false;
    let cancelled = false;

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const clearHeartbeat = () => {
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current);
        heartbeatTimerRef.current = null;
      }
    };

    const startHeartbeat = () => {
      clearHeartbeat();
      heartbeatTimerRef.current = setInterval(() => {
        const w = wsRef.current;
        if (!w) return;
        if (w.readyState !== WebSocket.OPEN) return;
        try {
          w.send(JSON.stringify({ type: "ping" }));
        } catch {
          /* socket is tearing down; onclose will handle it */
        }
      }, HEARTBEAT_INTERVAL_MS);
    };

    const scheduleReconnect = () => {
      if (intentionalCloseRef.current) return;
      if (reconnectAttemptRef.current >= MAX_RECONNECT) {
        setStatusLine("Ulanish muvaffaqiyatsiz. Sahifani yangilang.");
        setConn("disconnected");
        return;
      }
      const n = reconnectAttemptRef.current++;
      const delay = Math.min(30_000, BASE_DELAY_MS * 2 ** n);
      setStatusLine(`Qayta ulanish (${Math.round(delay / 1000)} s)…`);
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        if (!cancelled) connectSocket();
      }, delay);
    };

    const connectSocket = () => {
      if (cancelled) return;
      clearReconnectTimer();
      if (wsRef.current?.readyState === WebSocket.OPEN) return;
      if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

      setConn((c) => (recordingRef.current ? "recording" : "connecting"));
      setError(null);

      const url = defaultWsUrl();
      const ws = connectVoiceSocket(url, {
        onOpen: () => {
          reconnectAttemptRef.current = 0;
          setConn(recordingRef.current ? "recording" : "connected");
          const sid = optionsRef.current.speakerId;
          ws.send(
            JSON.stringify({
              type: "hello",
              sampleRate: 16000,
              encoding: "pcm_s16le",
              ...(sid ? { speakerId: sid } : {}),
            }),
          );
          setStatusLine("Serverga ulandi.");
          setPipelineStage(null);
          startHeartbeat();
        },
        onJson: (msg: ServerJsonMessage) => {
          if (msg.type === "status") {
            setStatusLine(msg.detail || msg.stage);
            const st = msg.stage;
            if (st === "idle") {
              expectingTtsRef.current = false;
              setPipelineStage(null);
            } else if (st === "stt" || st === "llm" || st === "tts") {
              setPipelineStage(st);
            }
          } else if (msg.type === "transcript") {
            const text = (msg.text || "").trim();
            if (text) {
              setMessages((prev) => [
                ...prev,
                { id: newId(), role: "user", content: text },
              ]);
              restHistoryRef.current = [
                ...restHistoryRef.current,
                { role: "user" as const, content: text },
              ].slice(-48);
            }
          } else if (msg.type === "reply_text") {
            const text = (msg.text || "").trim();
            if (text) {
              setMessages((prev) => [
                ...prev,
                { id: newId(), role: "assistant", content: text },
              ]);
              restHistoryRef.current = [
                ...restHistoryRef.current,
                { role: "assistant" as const, content: text },
              ].slice(-48);
            }
          } else if (msg.type === "audio_meta") {
            stopPlaybackOnly();
            const sr = msg.sampleRate || 24000;
            const p = new PcmPlayer(sr, { latencyHint: "playback" });
            playerRef.current = p;
            void p.ensureRunning();
            expectingTtsRef.current = true;
          } else if (msg.type === "error") {
            setError(`${msg.code}: ${msg.message}`);
          }
        },
        onBinary: (buf) => {
          if (expectingTtsRef.current && playerRef.current) {
            void playerRef.current.ensureRunning();
            playerRef.current.enqueue(buf);
          }
        },
        onClose: () => {
          wsRef.current = null;
          clearHeartbeat();
          if (!intentionalCloseRef.current) {
            setConn("disconnected");
            scheduleReconnect();
          } else {
            setConn("disconnected");
            setStatusLine("Ulanish uzildi.");
          }
        },
        onError: () => {
          setError("WebSocket xatolik.");
        },
      });

      wsRef.current = ws;
    };

    reconnectNowRef.current = () => {
      if (cancelled) return;
      reconnectAttemptRef.current = 0;
      clearReconnectTimer();
      connectSocket();
    };

    connectSocket();

    return () => {
      cancelled = true;
      intentionalCloseRef.current = true;
      clearReconnectTimer();
      clearHeartbeat();
      wsRef.current?.close();
      wsRef.current = null;
      reconnectNowRef.current = () => {};
      cleanupAudio();
    };
  }, [voiceBootstrapDone, cleanupAudio, stopPlaybackOnly]);

  const waitForSocketOpen = useCallback(async (timeoutMs: number): Promise<boolean> => {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (wsRef.current?.readyState === WebSocket.OPEN) return true;
      await new Promise((r) => setTimeout(r, 60));
    }
    return wsRef.current?.readyState === WebSocket.OPEN;
  }, []);

  const submitViaRest = useCallback(async (userText: string): Promise<void> => {
    // Tear down any WebAudio pipeline still holding TTS PCM chunks so the
    // HTMLAudioElement can take over cleanly.
    stopPlaybackOnly();

    setPipelineStage("llm");
    setStatusLine("Javob tayyorlanmoqda (REST)…");
    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: userText },
    ]);

    const MAX_HISTORY = 24;
    const history = restHistoryRef.current.slice(-MAX_HISTORY);
    const speakerId = optionsRef.current.speakerId;

    let resp: Response;
    try {
      resp = await apiFetch("/voice_reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: userText,
          ...(speakerId ? { speakerId } : {}),
          history,
        }),
      });
    } catch (e) {
      setPipelineStage(null);
      setError(e instanceof Error ? e.message : "Tarmoq xatoligi.");
      setStatusLine("Serverga ulanib bo‘lmadi.");
      return;
    }

    if (!resp.ok) {
      setPipelineStage(null);
      const detail = await resp.text().catch(() => `HTTP ${resp.status}`);
      setError(`Server xatoligi: ${detail.slice(0, 240)}`);
      setStatusLine("Xatolik.");
      return;
    }

    const replyTextRaw = resp.headers.get("X-Reply-Text") || "";
    let replyText = "";
    try {
      replyText = replyTextRaw ? decodeURIComponent(replyTextRaw) : "";
    } catch {
      replyText = replyTextRaw;
    }
    replyText = replyText.trim();

    setPipelineStage("tts");
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);

    if (replyText) {
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "assistant", content: replyText },
      ]);
      restHistoryRef.current = [
        ...restHistoryRef.current,
        { role: "user" as const, content: userText },
        { role: "assistant" as const, content: replyText },
      ].slice(-MAX_HISTORY * 2);
    }

    // Swap the previous object URL before reassigning so we don't leak blobs.
    if (fallbackAudioUrlRef.current) {
      URL.revokeObjectURL(fallbackAudioUrlRef.current);
    }
    fallbackAudioUrlRef.current = url;

    let audio = fallbackAudioRef.current;
    if (!audio) {
      audio = new Audio();
      audio.preload = "auto";
      fallbackAudioRef.current = audio;
    }
    audio.src = url;
    audio.onended = () => {
      setPipelineStage(null);
      setStatusLine("Tayyor.");
    };
    try {
      await audio.play();
      setStatusLine("Ijro etilmoqda…");
    } catch (e) {
      setPipelineStage(null);
      setError(
        e instanceof Error
          ? `Audio ijrosi bloklangan: ${e.message}`
          : "Audio ijrosi bloklangan.",
      );
    }
  }, [stopPlaybackOnly]);

  const deliverUserUtterance = useCallback(
    async (text: string) => {
      const t = text.trim();
      if (!t) {
        setStatusLine("Matn topilmadi, qayta urinib ko‘ring.");
        return;
      }
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        setStatusLine("Serverga qayta ulanmoqda…");
        reconnectNowRef.current();
        const ok = await waitForSocketOpen(WAIT_FOR_OPEN_MS);
        if (!ok) {
          await submitViaRest(t);
          return;
        }
      }
      wsRef.current!.send(JSON.stringify({ type: "text_utterance", text: t }));
    },
    [waitForSocketOpen, submitViaRest],
  );

  const stopMediaAndTranscribe = useCallback(async () => {
    recordingRef.current = false;
    captureModeRef.current = "idle";
    setConn("connected");
    setStatusLine("Matnga aylantirilmoqda…");
    setPipelineStage("stt");

    const rec = mediaRecorderRef.current;
    const stream = micStreamRef.current;
    mediaRecorderRef.current = null;
    const chunks = mediaChunksRef.current;
    mediaChunksRef.current = [];

    if (rec && rec.state !== "inactive") {
      await new Promise<void>((resolve) => {
        rec.onstop = () => resolve();
        try {
          rec.stop();
        } catch {
          resolve();
        }
      });
    }
    stream?.getTracks().forEach((tr) => tr.stop());
    micStreamRef.current = null;

    const blob = new Blob(chunks, {
      type: chunks[0]?.type || "audio/webm",
    });

    if (blob.size < 400) {
      setPipelineStage(null);
      setStatusLine("Audio juda qisqa. Qayta urinib ko‘ring.");
      return;
    }

    const fd = new FormData();
    const ext = blob.type.includes("webm")
      ? "webm"
      : blob.type.includes("mp4")
        ? "m4a"
        : "webm";
    fd.append("file", blob, `voice.${ext}`);

    try {
      const r = await apiFetch("/stt", { method: "POST", body: fd });
      if (!r.ok) {
        const detail = await r.text().catch(() => `HTTP ${r.status}`);
        setPipelineStage(null);
        setError(`STT: ${detail.slice(0, 240)}`);
        setStatusLine("Transkripsiya xatoligi.");
        return;
      }
      const data = (await r.json()) as { text?: string };
      const utterance = (data.text || "").trim();
      if (!utterance) {
        setPipelineStage(null);
        setStatusLine("Matn aniqlanmadi. Qayta gapiring.");
        return;
      }
      setPipelineStage(null);
      await deliverUserUtterance(utterance);
    } catch (e) {
      setPipelineStage(null);
      setError(e instanceof Error ? e.message : "STT tarmoq xatoligi.");
      setStatusLine("Transkripsiya muvaffaqiyatsiz.");
    }
  }, [deliverUserUtterance]);

  const startRecording = async () => {
    setError(null);

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setStatusLine("Serverga qayta ulanmoqda (fon rejimda)…");
      reconnectNowRef.current();
    }

    const opt = optionsRef.current;
    if (opt.interruptPlaybackOnRecord) {
      stopPlaybackOnly();
    }
    stopCaptureOnly();
    resetSpeechTranscript();

    const secure =
      typeof window !== "undefined" && window.isSecureContext;
    const hasMedia =
      secure &&
      typeof navigator !== "undefined" &&
      !!navigator.mediaDevices?.getUserMedia &&
      typeof MediaRecorder !== "undefined";

    if (hasMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            channelCount: 1,
          },
        });
        const mime = pickRecorderMime();
        const rec = mime
          ? new MediaRecorder(stream, { mimeType: mime })
          : new MediaRecorder(stream);
        micStreamRef.current = stream;
        mediaChunksRef.current = [];
        rec.ondataavailable = (ev) => {
          if (ev.data.size > 0) mediaChunksRef.current.push(ev.data);
        };
        rec.start(250);
        mediaRecorderRef.current = rec;
        captureModeRef.current = "media";
        recordingRef.current = true;
        setConn("recording");
        setStatusLine("Ovoz yozilmoqda… tugatish uchun yana bosing.");
        return;
      } catch (e) {
        micStreamRef.current?.getTracks().forEach((tr) => tr.stop());
        micStreamRef.current = null;
        const name =
          e instanceof DOMException
            ? e.name
            : e instanceof Error
              ? e.name
              : "";
        if (name === "NotAllowedError" || name === "PermissionDeniedError") {
          setError(MSG_MIC_DENIED);
          setConn("connected");
          return;
        }
        if (name === "NotFoundError") {
          setError("Mikrofon topilmadi. Qurilmani ulang.");
          setConn("connected");
          return;
        }
        // Boshqa xato: nutq API ga tushamiz
      }
    } else if (!secure && !speechSupported) {
      setError(MSG_HTTPS_NEEDED);
      setConn("connected");
      return;
    }

    if (!speechSupported) {
      setConn("connected");
      setError((prev) =>
        prev ??
        (!hasMedia
          ? "Brauzeringizda ovozli yozuv (mikrofon / nutq) qo‘llab-quvvatlanmaydi."
          : "Yozib bo‘lmadi."),
      );
      return;
    }

    captureModeRef.current = "speech";
    try {
      startSpeechListening();
      recordingRef.current = true;
      setConn("recording");
      setStatusLine("Tinglanmoqda… gapiring, tugatish uchun to‘xtating.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Tinglashni boshlab bo‘lmadi.");
      stopCaptureOnly();
      setConn("connected");
    }
  };

  const stopRecording = () => {
    if (captureModeRef.current === "media") {
      void stopMediaAndTranscribe();
      return;
    }

    stopSpeechListening();
    recordingRef.current = false;
    captureModeRef.current = "idle";
    setConn("connected");
    setStatusLine("Qayta ishlash…");

    window.setTimeout(() => {
      const text = finalTextRef.current.trim();
      if (!text) {
        setStatusLine("Matn eshitilmadi, qayta urinib ko‘ring.");
        return;
      }
      void deliverUserUtterance(text);
    }, 220);
  };

  const cancelRecording = () => {
    if (captureModeRef.current === "media") {
      mediaChunksRef.current = [];
      try {
        if (
          mediaRecorderRef.current &&
          mediaRecorderRef.current.state !== "inactive"
        ) {
          mediaRecorderRef.current.stop();
        }
      } catch {
        /* ignore */
      }
      mediaRecorderRef.current = null;
      micStreamRef.current?.getTracks().forEach((tr) => tr.stop());
      micStreamRef.current = null;
      captureModeRef.current = "idle";
      recordingRef.current = false;
      setConn("connected");
      setStatusLine("Bekor qilindi.");
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "cancel" }));
      }
      return;
    }

    stopCaptureOnly();
    resetSpeechTranscript();
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "cancel" }));
    }
    setConn("connected");
    setStatusLine("Bekor qilindi.");
  };

  const clearChat = () => {
    setMessages([]);
    setError(null);
    restHistoryRef.current = [];
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "reset_history" }));
    }
  };

  const toggleOption = <K extends keyof ChatOptions>(key: K, value: boolean) => {
    setOptions((o) => ({ ...o, [key]: value }));
  };

  const connLabel =
    conn === "connected"
      ? "Tayyor"
      : conn === "connecting"
        ? "Ulanmoqda"
        : conn === "recording"
          ? "Yozilmoqda"
          : "Uzilgan";

  const stageHint =
    pipelineStage === "stt"
      ? "Matnga aylantirilmoqda…"
      : pipelineStage === "llm"
        ? "Javob yozilmoqda…"
        : pipelineStage === "tts"
          ? "Ovoz chiqarilmoqda…"
          : null;

  const voiceBusy = conn === "connecting" || conn === "disconnected";

  const onVoiceOrbClick = () => {
    if (conn === "recording") {
      stopRecording();
      return;
    }
    if (conn === "connected") {
      void startRecording();
    }
  };

  return (
    <div className="flex h-[100dvh] w-full flex-col bg-[#f4f4f5] text-zinc-900 dark:bg-[#0d0d0d] dark:text-zinc-100">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-zinc-200/80 bg-white/90 px-4 py-3 backdrop-blur-md dark:border-zinc-800/80 dark:bg-zinc-950/90">
        <div className="min-w-0">
          <h1 className="truncate text-[15px] font-semibold tracking-tight">
            RealTimeVoice
          </h1>
          <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
            O‘zbek tilida ovozli suhbat
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {voices.length > 0 && (
            <label className="flex min-w-0 max-w-[11rem] items-center gap-1.5 sm:max-w-[14rem]">
              <span className="sr-only">Ovoz (klon)</span>
              <select
                value={options.speakerId ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  const id = v === "" ? null : v;
                  setOptions((o) => ({ ...o, speakerId: id }));
                  if (wsRef.current?.readyState === WebSocket.OPEN) {
                    wsRef.current.send(
                      JSON.stringify({
                        type: "set_speaker",
                        speakerId: id,
                      }),
                    );
                  }
                }}
                disabled={conn === "connecting" || conn === "disconnected"}
                className="max-w-full truncate rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-xs font-medium text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
              >
                <option value="">Standart (.env)</option>
                {voices.map((v) => (
                  <option key={v.id} value={v.id} title={v.id}>
                    {v.label} ({v.filename})
                  </option>
                ))}
              </select>
            </label>
          )}
          <Link
            href="/vositalar"
            className="rounded-lg border border-zinc-200 px-2.5 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            Vositalar
          </Link>
          <button
            type="button"
            onClick={() => setOptionsOpen(true)}
            className="rounded-lg border border-zinc-200 px-2.5 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            Sozlamalar
          </button>
          <button
            type="button"
            onClick={clearChat}
            className="rounded-lg border border-zinc-200 px-2.5 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            Tozalash
          </button>
          <span
            className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-xs font-medium text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            title={statusLine}
          >
            <span
              className={
                conn === "connected"
                  ? "h-2 w-2 rounded-full bg-emerald-500"
                  : conn === "recording"
                    ? "h-2 w-2 animate-pulse rounded-full bg-rose-500"
                    : conn === "connecting"
                      ? "h-2 w-2 animate-pulse rounded-full bg-amber-500"
                      : "h-2 w-2 rounded-full bg-zinc-400"
              }
            />
            {connLabel}
          </span>
        </div>
      </header>

      {insecureSite && (
        <div
          className="shrink-0 border-b border-amber-200/90 bg-amber-50 px-4 py-2 text-center text-xs leading-snug text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-100"
          role="status"
        >
          {MSG_HTTPS_NEEDED}
        </div>
      )}

      {optionsOpen && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/40 p-2 sm:p-4"
          role="presentation"
          onClick={() => setOptionsOpen(false)}
        >
          <aside
            className="flex h-full w-full max-w-sm flex-col rounded-2xl border border-zinc-200 bg-white shadow-2xl dark:border-zinc-700 dark:bg-zinc-900"
            role="dialog"
            aria-labelledby="rtv-options-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-700">
              <h2
                id="rtv-options-title"
                className="text-sm font-semibold text-zinc-900 dark:text-zinc-100"
              >
                Suhbat sozlamalari
              </h2>
              <button
                type="button"
                onClick={() => setOptionsOpen(false)}
                className="rounded-lg px-2 py-1 text-xs font-medium text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                Yopish
              </button>
            </div>
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4 text-sm text-zinc-700 dark:text-zinc-300">
              <p className="text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
                Mikrofon va javob ovozi alohida audio kontekstlarda ishlaydi:
                yozishni tugatgach ham TTS tinglash mumkin (asinxron muhit).
              </p>

              <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-zinc-200 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-800/40">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-emerald-600"
                  checked={options.interruptPlaybackOnRecord}
                  onChange={(e) =>
                    toggleOption("interruptPlaybackOnRecord", e.target.checked)
                  }
                />
                <span>
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">
                    Yangi yozishda javobni to‘xtatish
                  </span>
                  <span className="mt-0.5 block text-xs text-zinc-500 dark:text-zinc-400">
                    Yozishni boshlashda avvalgi ovozli javob to‘xtatiladi
                    (barge-in).
                  </span>
                </span>
              </label>

              <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-zinc-200 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-800/40">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-emerald-600"
                  checked={options.autoScroll}
                  onChange={(e) => toggleOption("autoScroll", e.target.checked)}
                />
                <span>
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">
                    Avtomatik pastga scroll
                  </span>
                  <span className="mt-0.5 block text-xs text-zinc-500 dark:text-zinc-400">
                    Yangi xabar yoki holatda suhbat oxiriga siljiydi.
                  </span>
                </span>
              </label>

              <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-zinc-200 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-800/40">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-emerald-600"
                  checked={options.showPipelineStage}
                  onChange={(e) =>
                    toggleOption("showPipelineStage", e.target.checked)
                  }
                />
                <span>
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">
                    Jarayon ko‘rsatkichi
                  </span>
                  <span className="mt-0.5 block text-xs text-zinc-500 dark:text-zinc-400">
                    STT / LLM / TTS bosqichida kichik yuklanish chiptasi.
                  </span>
                </span>
              </label>

              <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-zinc-200 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-800/40">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-emerald-600"
                  checked={options.lowLatencyCapture}
                  onChange={(e) =>
                    toggleOption("lowLatencyCapture", e.target.checked)
                  }
                />
                <span>
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">
                    Tezkor mikrofon (interactive)
                  </span>
                  <span className="mt-0.5 block text-xs text-zinc-500 dark:text-zinc-400">
                    Brauzer `latencyHint: interactive` — yozuvni boshqarishga
                    mos; ba’zi qurilmalarda barqarorlik boshqacha bo‘lishi
                    mumkin.
                  </span>
                </span>
              </label>
            </div>
          </aside>
        </div>
      )}

      <div
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-y-auto px-3 py-4 sm:px-4"
      >
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-3 pb-4">
          {messages.length === 0 && (
            <div className="mx-auto mt-8 max-w-md rounded-2xl border border-dashed border-zinc-300 bg-white/60 px-5 py-8 text-center text-sm text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-400">
              <p className="font-medium text-zinc-800 dark:text-zinc-200">
                Ovozli suhbat
              </p>
              <p className="mt-2 leading-relaxed">
                Pastdagi mikrofonni bosing, gapiring, qayta bosing — xabar yuboriladi
                va javob ovozda ijro etiladi (ChatGPT Voice uslubida).
              </p>
            </div>
          )}

          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="flex justify-end">
                <div
                  className="max-w-[min(85%,28rem)] rounded-[1.35rem] rounded-br-md bg-zinc-900 px-4 py-2.5 text-[15px] leading-relaxed text-white shadow-sm dark:bg-zinc-700 dark:text-zinc-50"
                  role="article"
                >
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={m.id} className="flex justify-start">
                <div className="flex max-w-[min(92%,36rem)] gap-3">
                  <div
                    className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#10a37f]/15 text-xs font-bold text-[#0d8f6e] ring-1 ring-[#10a37f]/25 dark:bg-[#10a37f]/20 dark:text-emerald-300 dark:ring-[#10a37f]/30"
                    aria-hidden
                  >
                    AI
                  </div>
                  <div
                    className="rounded-[1.35rem] rounded-bl-md bg-white px-4 py-2.5 text-[15px] leading-relaxed text-zinc-800 shadow-sm ring-1 ring-zinc-200/80 dark:bg-zinc-800/90 dark:text-zinc-100 dark:ring-zinc-700/60"
                    role="article"
                  >
                    {m.content}
                  </div>
                </div>
              </div>
            ),
          )}

          {options.showPipelineStage && stageHint && (
            <div className="flex justify-start pl-11">
              <div className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white/90 px-3 py-1.5 text-xs text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900/80 dark:text-zinc-400">
                <span className="flex gap-0.5">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.2s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.1s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400" />
                </span>
                {stageHint}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="shrink-0 rounded-t-3xl border-t border-zinc-200/90 bg-[#ececf1] px-4 pb-6 pt-4 shadow-[0_-4px_24px_rgba(0,0,0,0.06)] dark:border-zinc-800/90 dark:bg-[#1a1a1a] dark:shadow-[0_-4px_24px_rgba(0,0,0,0.35)]">
        <div className="mx-auto flex w-full max-w-3xl flex-col items-center gap-3">
          {error && (
            <div
              className="w-full rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/50 dark:text-rose-100"
              role="alert"
            >
              {error}
            </div>
          )}

          <p className="line-clamp-2 min-h-[2.5rem] max-w-md text-center text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">
            {statusLine}
          </p>

          <div className="flex w-full flex-col items-center gap-4">
            <div className="flex items-end justify-center gap-3">
              {conn === "recording" && (
                <div
                  className="mb-2 flex h-10 items-end justify-center gap-0.5"
                  aria-hidden
                >
                  {[3, 6, 4, 8, 5, 7, 4].map((h, i) => (
                    <span
                      key={i}
                      className="w-1 animate-bounce rounded-full bg-rose-500 dark:bg-rose-400"
                      style={{
                        height: `${h * 2}px`,
                        animationDuration: "0.7s",
                        animationDelay: `${i * 0.08}s`,
                      }}
                    />
                  ))}
                </div>
              )}

              <button
                type="button"
                onClick={onVoiceOrbClick}
                disabled={voiceBusy}
                aria-label={
                  conn === "recording"
                    ? "Yuborish va to‘xtatish"
                    : "Yozishni boshlash"
                }
                className="group relative flex h-[4.75rem] w-[4.75rem] shrink-0 items-center justify-center rounded-full outline-none transition-transform focus-visible:ring-2 focus-visible:ring-emerald-500/80 focus-visible:ring-offset-2 focus-visible:ring-offset-[#ececf1] disabled:cursor-not-allowed disabled:opacity-40 dark:focus-visible:ring-offset-[#1a1a1a]"
              >
                {conn === "recording" && (
                  <span
                    className="absolute inset-[-6px] animate-ping rounded-full bg-rose-400/35 dark:bg-rose-500/25"
                    aria-hidden
                  />
                )}
                <span
                  className={`relative flex h-[3.65rem] w-[3.65rem] items-center justify-center rounded-full shadow-lg transition-transform group-active:scale-95 ${
                    conn === "recording"
                      ? "bg-rose-600 shadow-rose-600/35"
                      : "bg-[#10a37f] shadow-black/15 dark:shadow-black/40"
                  }`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src="/voice-mic.png"
                    alt=""
                    width={36}
                    height={36}
                    className="h-9 w-9 object-contain brightness-0 invert"
                  />
                </span>
              </button>

              {conn === "recording" && (
                <div
                  className="mb-2 flex h-10 items-end justify-center gap-0.5"
                  aria-hidden
                >
                  {[5, 8, 4, 7, 3, 6, 4].map((h, i) => (
                    <span
                      key={`r-${i}`}
                      className="w-1 animate-bounce rounded-full bg-rose-500 dark:bg-rose-400"
                      style={{
                        height: `${h * 2}px`,
                        animationDuration: "0.65s",
                        animationDelay: `${0.2 + i * 0.07}s`,
                      }}
                    />
                  ))}
                </div>
              )}
            </div>

            <p className="text-center text-[11px] text-zinc-500 dark:text-zinc-500">
              {conn === "recording"
                ? "Qayta bosing — yuboriladi"
                : voiceBusy
                  ? "Serverga ulanmoqda…"
                  : "Bosing — tinglash boshlanadi"}
            </p>

            <button
              type="button"
              onClick={cancelRecording}
              disabled={conn !== "recording"}
              className="text-xs font-medium text-zinc-500 underline decoration-zinc-400/70 underline-offset-2 hover:text-zinc-700 disabled:pointer-events-none disabled:opacity-30 dark:text-zinc-500 dark:hover:text-zinc-300"
            >
              Bekor qilish
            </button>
          </div>
        </div>
      </div>

    </div>
  );
}
