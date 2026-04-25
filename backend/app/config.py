import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    frontend_origin: str = "http://localhost:3000"

    # STT (defaults tuned for Uzbek voice: larger model + beam + language lock)
    # Accepts an official Whisper size ("small", "large-v3", ...), a local CTranslate2
    # directory, or a HF repo id like "islomov/rubaistt_v2_medium" — HF repos are
    # auto-downloaded and converted to CT2 on first use (cached in stt_model_cache_dir).
    stt_model_size: str = "small"
    # Where auto-converted CT2 checkpoints are cached (repo-root relative or absolute).
    stt_model_cache_dir: str = "models/whisper_ct2"
    # CT2 quantization used when converting HF Whisper fine-tunes (float16 on GPU, int8_float16 on CPU works too).
    stt_ct2_quantization: str = "float16"
    stt_device: str = "auto"
    stt_compute_type: str = "default"
    stt_language: str = "uz"
    # Beam 6–8 improves Uzbek vs greedy; higher = slower (GPU recommended for medium+)
    stt_beam_size: int = 7
    stt_best_of: int = 1
    stt_without_timestamps: bool = True
    # Longer Uzbek Latin context reduces garbled / pseudo-Turkic spellings (empty = omit)
    stt_initial_prompt: str = (
        "O\u2019zbekiston Respublikasi, Toshkent shahri. Men siz bilan o\u2019zbek tilida "
        "gaplashyapman. Bugun havo yaxshi, lekin ertaga yomg\u2019ir yog\u2019ishi mumkin. "
        "Haqiqiy, ishonchli, ravon va tushunarli javob bering. Chunki bu muhim, ammo "
        "hech qachon shoshilinch emas. Rahmat, iltimos, xayr. Qanday yordam berishim "
        "mumkin? Men bilmayman deyish ham normal. So\u2019z, gap, tushuncha, xalq, maktab, "
        "universitet, ish, dam olish, sog\u2019liq, oila, do\u2019stlar."
    )
    # Bias toward common Uzbek spellings (faster-whisper hotwords; empty = omit)
    stt_hotwords: str = (
        "haqiqiy haqiqat emas chunki ammo lekin shuning uchun unda shunda qachon qayerda "
        "qanday nima kim nima uchun men siz biz ular u bu shu bir ikki uch besh olti "
        "yoq ha yoq rahmat iltimos kechirasiz tushundim tushunmadim gapiring tinglayapman "
        "ishonaman ishonmayman mumkin mumkin emas juda yaxshi yomon"
    )
    stt_vad_filter: bool = True
    # JSON object of Silero VAD params, e.g. {"min_silence_duration_ms": 500}
    stt_vad_parameters_json: str = ""
    # Anti-hallucination / repetition (faster-whisper)
    stt_patience: float = 1.15
    stt_repetition_penalty: float = 1.08
    stt_no_repeat_ngram_size: int = 3
    # Stricter than 2.4 to catch repetitive gibberish; raise in .env if legit speech gets dropped
    stt_compression_ratio_threshold: float = 2.2
    # Optional decode overrides (None = omit, use faster-whisper defaults)
    stt_temperature: Optional[float] = None
    stt_log_prob_threshold: Optional[float] = None
    # False reduces “stuck loop” garbage on short phrases; True for long dictation continuity
    stt_condition_on_previous_text: bool = False
    max_audio_seconds: float = 60.0
    max_audio_bytes: int = 60 * 16000 * 2

    # Hugging Face (downloads / gated models; also respected by huggingface-cli)
    hf_token: str = ""

    # TTS backend: ``omnivoice`` (local voice-clone, 10-80s on consumer GPU),
    # ``edge`` (Microsoft Edge neural TTS, ~1-2s, native Uzbek voices, free).
    # Change to ``edge`` for real-time chat on a laptop. Value is normalized
    # case-insensitively at runtime by :func:`app.services.tts.active_backend`.
    tts_backend: str = "omnivoice"
    # Edge TTS voice id (see tts_edge.UZBEK_VOICES). Only used when tts_backend=edge.
    tts_edge_voice: str = "uz-UZ-MadinaNeural"

    # TTS (OmniVoice)
    omnivoice_model_id: str = "k2-fsa/OmniVoice"
    tts_device_map: str = "cpu"
    tts_dtype: str = "float16"
    # Diffusion/flow-matching denoising steps. Time-per-utterance scales linearly.
    # 6–8 is a good sweet spot on GPU for chat replies; 10–14 for audiobook-grade.
    tts_num_steps: int = 8
    tts_speed: float = 1.05
    # Sentence-level streaming for /ws/voice: each chunk is synthesized and sent
    # before the next starts, so the user hears the first sentence while the rest
    # is still being generated. Set tts_stream_segments=false to disable.
    tts_stream_segments: bool = True
    tts_stream_min_chars: int = 40
    tts_stream_max_chars: int = 220
    # Warmup triggers OmniVoice's lazy Whisper-large-v3-turbo load at app startup
    # instead of the first user-visible TTS call (saves ~20–30 s on the first reply).
    tts_warmup_on_start: bool = True
    tts_warmup_text: str = "Salom."
    # Optional natural-language style hint (Uzbek Latin, spoken delivery)
    tts_instruct: str = (
        "O‘zbek lotin alifbosi bilan tabiiy, ravon nutq; jumlalar qisqa va tushunarli bo‘lsin."
    )
    tts_ref_audio_path: str = ""
    tts_ref_text: str = ""
    # Repo-relative directory scanned at startup for WAV/FLAC/OGG reference clips (myVoice)
    tts_voices_scan_dir: str = "myVoice"

    # LLM
    llm_provider: Literal["openai", "ollama"] = "openai"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    # Ollama options.num_predict (shorter replies = lower latency). 0 = omit (no cap).
    ollama_num_predict: int = 256
    llm_timeout_seconds: float = 120.0
    # OpenAI max completion tokens; 0 = omit (no explicit cap).
    openai_max_tokens: int = 256
    # Max prior user+assistant messages kept per WebSocket (not counting current user).
    llm_history_max_messages: int = 24

    # Optional shared secret: require matching `?token=` on /ws/voice and X-API-Key (or Bearer) on REST when set.
    api_shared_secret: str = ""

    # WebSocket TTS streaming
    tts_pcm_chunk_ms: int = 32


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    token = (s.hf_token or "").strip()
    if token:
        os.environ["HF_TOKEN"] = token
        os.environ["HUGGING_FACE_HUB_TOKEN"] = token
    return s
