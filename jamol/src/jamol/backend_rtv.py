"""
In-process RealTimeVoice stack (same ``app.services`` as uvicorn).
Use when ``--embedded-audio`` is set or as fallback; default is HTTP :class:`jamol.api_client.RealTimeVoiceApi`.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from jamol.audio_io import play_wav_bytes, record_wav_bytes

logger = logging.getLogger(__name__)

_settings_cache: Any | None = None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def backend_app_dir() -> Path:
    return repo_root() / "backend"


def ensure_backend_import_path() -> None:
    b = backend_app_dir()
    if not (b / "app" / "config.py").is_file():
        raise RuntimeError(
            f"Backend package not found at {b / 'app'}. "
            "Run Jamol from the RealTimeVoice repository layout."
        )
    key = str(b.resolve())
    if key not in sys.path:
        sys.path.insert(0, key)


def load_backend_settings() -> Any:
    global _settings_cache
    ensure_backend_import_path()
    from app.config import get_settings

    if _settings_cache is None:
        _settings_cache = get_settings()
    return _settings_cache


def record_and_transcribe(
    settings: Any,
    *,
    max_seconds: float,
    sample_rate: int = 16000,
) -> str:
    """Record mic → temp WAV → ``stt.transcribe_file`` (same as ``POST /stt`` on server)."""
    from app.services import stt as stt_svc

    cap = float(min(max(max_seconds, 1.0), 120.0))
    wav = record_wav_bytes(max_seconds=cap, sample_rate=sample_rate)
    if not wav:
        return ""

    stt_svc.init_model(settings)
    path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        with open(path, "wb") as f:
            f.write(wav)
        text = stt_svc.transcribe_file(Path(path), settings)
        return (text or "").strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def transcribe_pcm_embedded(
    pcm_s16le: bytes,
    sample_rate: int,
    settings: Any,
) -> str:
    """Run PCM through in-process ``stt.transcribe_pcm`` (no HTTP round-trip)."""
    from app.services import stt as stt_svc

    if not pcm_s16le:
        return ""
    stt_svc.init_model(settings)
    text = stt_svc.transcribe_pcm(pcm_s16le, int(sample_rate), settings)
    return (text or "").strip()


def speak_omnivoice(text: str, settings: Any) -> None:
    """``tts.text_to_speech_wav_bytes`` + play (same bytes as ``POST /tts``)."""
    if not (text or "").strip():
        return
    from app.services import tts as tts_svc

    tts_svc.init_model(settings)
    wav = tts_svc.text_to_speech_wav_bytes(text.strip(), settings)
    play_wav_bytes(wav)


def try_load_backend_settings() -> Any | None:
    try:
        return load_backend_settings()
    except Exception as e:
        logger.debug("Embedded backend unavailable: %s", e)
        return None
