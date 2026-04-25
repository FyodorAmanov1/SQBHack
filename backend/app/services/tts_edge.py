"""
Microsoft Edge neural TTS backend — free, Uzbek-native, real-time.

Why this exists: OmniVoice (flow-matching + internal Whisper-v3-turbo) takes
10–80 s per utterance on a consumer GPU. Edge TTS returns 24 kHz mono MP3 from
Azure's neural endpoint in ~1–2 s end-to-end and supports Uzbek out of the box
with two Microsoft voices. No GPU, no HF weights, no auth.

Output contract (matches :mod:`app.services.tts` for drop-in use):

- PCM sample rate: **24 000 Hz**, mono, int16 little-endian.
- ``synthesize_pcm_bytes`` returns the full utterance as PCM bytes.
- ``stream_pcm_chunks`` yields PCM bytes as soon as Edge + the MP3 decoder
  produce them, so the WebSocket can forward them to the browser without
  waiting for the whole reply.
"""

from __future__ import annotations

import io
import logging
from typing import AsyncIterator

import av  # PyAV — bundles its own ffmpeg libs, so no system install needed.
import edge_tts
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


# Microsoft's Uzbek voices on the Edge Read-Aloud endpoint (verified 2026).
UZBEK_VOICES: list[dict[str, str]] = [
    {
        "id": "uz-UZ-MadinaNeural",
        "short_name": "uz-UZ-MadinaNeural",
        "name": "Madina",
        "gender": "Female",
        "locale": "uz-UZ",
        "label": "Madina — Uzbek (female, Microsoft)",
    },
    {
        "id": "uz-UZ-SardorNeural",
        "short_name": "uz-UZ-SardorNeural",
        "name": "Sardor",
        "gender": "Male",
        "locale": "uz-UZ",
        "label": "Sardor — Uzbek (male, Microsoft)",
    },
]

DEFAULT_UZ_VOICE = "uz-UZ-MadinaNeural"
EDGE_SAMPLE_RATE = 24_000


def uzbek_voice_ids() -> list[str]:
    return [v["id"] for v in UZBEK_VOICES]


def resolve_voice(voice_ref: str | None) -> str:
    """Return a valid Edge voice id — accepts short names, a locale prefix, or ``None``."""
    raw = (voice_ref or "").strip()
    if not raw:
        return DEFAULT_UZ_VOICE
    ids = uzbek_voice_ids()
    if raw in ids:
        return raw
    lowered = raw.lower()
    for v in UZBEK_VOICES:
        if v["id"].lower() == lowered or v["name"].lower() == lowered:
            return v["id"]
    # Allow bare "male"/"female"/"ayol"/"erkak" shortcuts.
    if lowered in {"female", "ayol", "xotin", "madina"}:
        return "uz-UZ-MadinaNeural"
    if lowered in {"male", "erkak", "sardor"}:
        return "uz-UZ-SardorNeural"
    # Anything starting with a non-Uzbek locale is still forwarded; Edge rejects unknowns cleanly.
    if "-" in raw:
        return raw
    return DEFAULT_UZ_VOICE


def rate_string_from_speed(speed: float) -> str:
    """Convert a ``0.5`` … ``2.0`` multiplier into Edge's ``"+N%"`` / ``"-N%"`` format."""
    try:
        pct = int(round((float(speed) - 1.0) * 100))
    except (TypeError, ValueError):
        pct = 0
    pct = max(-50, min(100, pct))  # Edge rejects anything outside roughly this band.
    return f"{pct:+d}%"


def _decode_mp3_to_pcm(mp3_bytes: bytes) -> bytes:
    """Decode an MP3 blob to little-endian 16-bit PCM mono @ 24 kHz."""
    if not mp3_bytes:
        return b""
    container = av.open(io.BytesIO(mp3_bytes), mode="r", format="mp3")
    try:
        audio_stream = container.streams.audio[0]
        resampler = av.AudioResampler(
            format="s16", layout="mono", rate=EDGE_SAMPLE_RATE
        )
        out = bytearray()
        for frame in container.decode(audio_stream):
            for rf in resampler.resample(frame):
                arr = rf.to_ndarray()
                if arr.ndim == 2:
                    arr = arr.flatten()
                out.extend(arr.tobytes())
        # Flush resampler tail (small number of samples).
        for rf in resampler.resample(None):
            arr = rf.to_ndarray()
            if arr.ndim == 2:
                arr = arr.flatten()
            out.extend(arr.tobytes())
    finally:
        container.close()
    return bytes(out)


async def _collect_mp3(text: str, voice: str, rate: str) -> bytes:
    """Drive :class:`edge_tts.Communicate` to completion and return the MP3 blob."""
    if not text.strip():
        return b""
    communicate = edge_tts.Communicate(text.strip(), voice, rate=rate)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            data = chunk.get("data")
            if data:
                buf.extend(data)
    return bytes(buf)


async def synthesize_pcm_bytes(
    text: str,
    *,
    voice: str | None = None,
    speed: float = 1.0,
) -> tuple[bytes, int]:
    """
    Synthesize ``text`` and return ``(pcm_s16le_bytes, sample_rate=24000)``.

    Raises :class:`RuntimeError` on network / Azure errors so the caller can
    surface them over the WebSocket instead of silently returning silence.
    """
    if not text.strip():
        return b"", EDGE_SAMPLE_RATE
    v = resolve_voice(voice)
    rate = rate_string_from_speed(speed)
    try:
        mp3 = await _collect_mp3(text, v, rate)
    except Exception as e:
        raise RuntimeError(f"Edge TTS network failure ({v}, rate={rate}): {e}") from e
    if not mp3:
        raise RuntimeError(
            f"Edge TTS returned no audio for voice={v!r} (is the voice id valid?)"
        )
    pcm = _decode_mp3_to_pcm(mp3)
    return pcm, EDGE_SAMPLE_RATE


async def synthesize_wav_bytes(
    text: str,
    *,
    voice: str | None = None,
    speed: float = 1.0,
) -> bytes:
    """Synthesize → WAV (PCM_16, 24 kHz, mono). Used by ``POST /tts``."""
    pcm, sr = await synthesize_pcm_bytes(text, voice=voice, speed=speed)
    if not pcm:
        return b""
    samples = np.frombuffer(pcm, dtype=np.int16)
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


async def stream_pcm_chunks(
    text: str,
    *,
    voice: str | None = None,
    speed: float = 1.0,
    chunk_samples: int = 768,
) -> AsyncIterator[bytes]:
    """
    Async-generator: yields ``chunk_samples * 2`` raw PCM bytes per iteration
    as audio becomes available. Currently collects the full MP3 and then
    emits PCM chunks; edge-tts delivers MP3 at roughly real-time, so for a
    5-sentence reply the WS pipeline should still begin playing after the
    first sentence (the caller is expected to split before this).
    """
    pcm, _ = await synthesize_pcm_bytes(text, voice=voice, speed=speed)
    if not pcm:
        return
    step = max(2, int(chunk_samples) * 2)
    for i in range(0, len(pcm), step):
        yield pcm[i : i + step]
