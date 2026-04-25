const STORAGE_KEY_V2 = "rtv_chat_options_v2";
const STORAGE_KEY_V1 = "rtv_chat_options_v1";

export type ChatOptions = {
  /** Stop TTS playback when starting a new recording (barge-in). */
  interruptPlaybackOnRecord: boolean;
  /** Scroll the thread when new messages or status arrive. */
  autoScroll: boolean;
  /** Show the small STT/LLM/TTS progress chip under messages. */
  showPipelineStage: boolean;
  /** Use a lower-latency capture graph (browser hint only). */
  lowLatencyCapture: boolean;
  /**
   * GET /voices entry `id` (repo-relative path), e.g. myVoice/a.wav.
   * null = use server default (TTS_REF_AUDIO_PATH from .env only).
   */
  speakerId: string | null;
};

export const defaultChatOptions: ChatOptions = {
  interruptPlaybackOnRecord: true,
  autoScroll: true,
  showPipelineStage: true,
  lowLatencyCapture: true,
  speakerId: null,
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function loadChatOptions(): ChatOptions {
  if (typeof window === "undefined") return { ...defaultChatOptions };
  try {
    let raw = window.localStorage.getItem(STORAGE_KEY_V2);
    if (!raw) raw = window.localStorage.getItem(STORAGE_KEY_V1);
    if (!raw) return { ...defaultChatOptions };
    const o = JSON.parse(raw) as unknown;
    if (!isRecord(o)) return { ...defaultChatOptions };
    let speakerId: string | null = defaultChatOptions.speakerId;
    if (typeof o.speakerId === "string") speakerId = o.speakerId;
    else if (o.speakerId === null) speakerId = null;
    return {
      interruptPlaybackOnRecord:
        typeof o.interruptPlaybackOnRecord === "boolean"
          ? o.interruptPlaybackOnRecord
          : defaultChatOptions.interruptPlaybackOnRecord,
      autoScroll:
        typeof o.autoScroll === "boolean"
          ? o.autoScroll
          : defaultChatOptions.autoScroll,
      showPipelineStage:
        typeof o.showPipelineStage === "boolean"
          ? o.showPipelineStage
          : defaultChatOptions.showPipelineStage,
      lowLatencyCapture:
        typeof o.lowLatencyCapture === "boolean"
          ? o.lowLatencyCapture
          : defaultChatOptions.lowLatencyCapture,
      speakerId,
    };
  } catch {
    return { ...defaultChatOptions };
  }
}

export function saveChatOptions(options: ChatOptions): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY_V2, JSON.stringify(options));
  } catch {
    /* quota / private mode */
  }
}
