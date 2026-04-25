from __future__ import annotations

import io
import logging
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

import numpy as np
import soundfile as sf
import torch

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

_model = None
_ref_logged = False
# Cache key = (resolved_path, mtime_ns); value = (waveform_tensor, sample_rate).
# Loaded once, reused for every ``generate(...)`` until the file changes on disk.
_ref_cache: dict[tuple[str, int], tuple[torch.Tensor, int]] = {}
_ref_cache_lock = threading.Lock()
_ref_cache_hits = 0  # exposed for tests/metrics; purely informational


def _load_ref_waveform_uncached(ref_path: str) -> tuple[torch.Tensor, int]:
    """Load reference WAV with soundfile so OmniVoice never calls torchaudio.load (TorchCodec)."""
    data, sr = sf.read(ref_path, dtype="float32", always_2d=True)
    if data.ndim != 2:
        data = np.atleast_2d(data)
    if data.shape[1] > 1:
        data = np.mean(data, axis=1, keepdims=True)
    wave = torch.from_numpy(np.ascontiguousarray(data.T))
    return wave, int(sr)


def _ref_audio_waveform_tuple(ref_path: str) -> tuple[torch.Tensor, int]:
    """Cached variant of :func:`_load_ref_waveform_uncached`, keyed on path + mtime_ns."""
    global _ref_cache_hits
    try:
        mtime_ns = Path(ref_path).stat().st_mtime_ns
    except OSError:
        # File disappeared between resolve and read: fall back to a fresh load so
        # the caller sees the underlying error naturally.
        return _load_ref_waveform_uncached(ref_path)
    key = (ref_path, mtime_ns)
    with _ref_cache_lock:
        cached = _ref_cache.get(key)
        if cached is not None:
            _ref_cache_hits += 1
            return cached
    loaded = _load_ref_waveform_uncached(ref_path)
    with _ref_cache_lock:
        # Another thread may have populated concurrently; prefer the existing entry
        # so we don't hold two tensors for the same clip.
        existing = _ref_cache.get(key)
        if existing is not None:
            _ref_cache_hits += 1
            return existing
        _ref_cache[key] = loaded
    return loaded


def clear_ref_cache() -> None:
    """Drop all cached reference waveforms (tests + forced reload after file edits)."""
    global _ref_cache_hits
    with _ref_cache_lock:
        _ref_cache.clear()
        _ref_cache_hits = 0


def ref_cache_hits() -> int:
    """Number of times a cached ref waveform was reused (monotonic counter)."""
    return _ref_cache_hits


def _resolve_ref_audio_path(raw: str) -> str | None:
    """Absolute path, cwd-relative, backend-relative, or repo-root-relative (uvicorn cwd is often `backend/`)."""
    p = Path(raw.strip()).expanduser()
    if p.is_file():
        return str(p.resolve())
    backend_dir = Path(__file__).resolve().parents[2]
    repo_root = backend_dir.parent
    for base in (Path.cwd(), repo_root, backend_dir):
        cand = (base / raw.strip()).resolve()
        if cand.is_file():
            return str(cand)
    logger.warning("TTS_REF_AUDIO_PATH not found (tried cwd, repo root, backend): %s", raw)
    return None


def _torch_dtype(name: str):
    n = (name or "float16").lower()
    if n in ("float16", "fp16"):
        return torch.float16
    if n in ("bfloat16", "bf16"):
        return torch.bfloat16
    return torch.float32


def active_backend(settings: Settings) -> str:
    """Normalized TTS backend id: ``"omnivoice"`` or ``"edge"``."""
    raw = (getattr(settings, "tts_backend", None) or "omnivoice").strip().lower()
    if raw not in {"omnivoice", "edge"}:
        logger.warning("Unknown TTS_BACKEND=%r; falling back to omnivoice.", raw)
        return "omnivoice"
    return raw


def init_model(settings: Settings) -> None:
    """Load the heavy OmniVoice weights only when that backend is selected.

    Edge TTS makes HTTPS calls to Azure and needs no local weights, so starting
    the server with ``TTS_BACKEND=edge`` skips the multi-gigabyte download /
    GPU allocation entirely — important for running on machines without CUDA.
    """
    global _model
    if _model is not None:
        return
    if active_backend(settings) != "omnivoice":
        logger.info(
            "TTS_BACKEND=%s: skipping OmniVoice load (no local weights needed).",
            active_backend(settings),
        )
        return
    from omnivoice import OmniVoice

    device_map = settings.tts_device_map
    dtype = _torch_dtype(settings.tts_dtype)
    if device_map == "cpu" and dtype == torch.float16:
        dtype = torch.float32
        logger.info("TTS on CPU: using float32 instead of float16")
    logger.info(
        "Loading OmniVoice model=%s device_map=%s dtype=%s",
        settings.omnivoice_model_id,
        device_map,
        dtype,
    )
    try:
        _model = OmniVoice.from_pretrained(
            settings.omnivoice_model_id,
            device_map=device_map,
            torch_dtype=dtype,
        )
    except TypeError:
        _model = OmniVoice.from_pretrained(
            settings.omnivoice_model_id,
            device_map=device_map,
            dtype=dtype,
        )


def _build_generate_kwargs(
    settings: Settings,
    text: str,
    *,
    voice_ref_path: str | None = None,
) -> dict:
    global _ref_logged
    kw: dict = {
        "text": text,
        "num_step": settings.tts_num_steps,
        "speed": settings.tts_speed,
    }
    ref_raw = (voice_ref_path or "").strip() or (settings.tts_ref_audio_path or "").strip()
    ref_text_for_kw: str | None = None
    if voice_ref_path and voice_ref_path.strip():
        from app.services import voices as voices_svc

        side = voices_svc.optional_ref_text_for_audio(
            voice_ref_path.strip().replace("\\", "/")
        )
        if side is not None:
            ref_text_for_kw = side
        else:
            ref_text_for_kw = None
    else:
        rt = (settings.tts_ref_text or "").strip()
        ref_text_for_kw = rt if rt else None

    if ref_raw and _model is not None:
        ref_path = _resolve_ref_audio_path(ref_raw)
        if ref_path:
            try:
                # Tuple path: OmniVoice skips torchaudio.load → no torchcodec required.
                kw["ref_audio"] = _ref_audio_waveform_tuple(ref_path)
            except Exception:
                logger.exception(
                    "TTS: could not load reference audio with soundfile; clone disabled"
                )
            else:
                if ref_text_for_kw:
                    kw["ref_text"] = ref_text_for_kw
                if not _ref_logged:
                    logger.info(
                        "TTS: voice clone from %s (loaded via soundfile, not torchaudio)",
                        ref_path,
                    )
                    _ref_logged = True
    instruct = (settings.tts_instruct or "").strip()
    if instruct:
        kw["instruct"] = instruct
    return kw


def synthesize_to_tensor(
    text: str,
    settings: Settings,
    *,
    voice_ref_path: str | None = None,
) -> torch.Tensor:
    if _model is None:
        raise RuntimeError("TTS model not initialized")
    if not text.strip():
        raise ValueError("Empty text for TTS")
    kw = _build_generate_kwargs(
        settings, text.strip(), voice_ref_path=voice_ref_path
    )
    audio = _model.generate(**kw)
    if isinstance(audio, (list, tuple)):
        wave = audio[0]
    else:
        wave = audio
    if not isinstance(wave, torch.Tensor):
        wave = torch.as_tensor(wave)
    if wave.dim() == 1:
        wave = wave.unsqueeze(0)
    return wave


def text_to_speech_wav_bytes(
    text: str,
    settings: Settings,
    *,
    voice_ref_path: str | None = None,
) -> bytes:
    """WAV bytes (PCM_16 @ 24 kHz). Dispatches to the active backend (OmniVoice or Edge)."""
    if active_backend(settings) == "edge":
        import asyncio

        from app.services import tts_edge

        voice = voice_ref_path or settings.tts_edge_voice
        try:
            return asyncio.run(
                tts_edge.synthesize_wav_bytes(
                    text, voice=voice, speed=settings.tts_speed
                )
            )
        except RuntimeError as e:
            # asyncio.run fails if called from an already-running loop; for sync callers
            # (e.g. embedded Jamol) we're outside the loop so this should be safe.
            logger.exception("Edge TTS failed: %s", e)
            raise

    wave = synthesize_to_tensor(text, settings, voice_ref_path=voice_ref_path)
    w = wave.detach().cpu().float().squeeze()
    if w.dim() == 2:
        w = w.T  # (channels, time) -> (time, channels) for soundfile
    elif w.dim() != 1:
        w = w.flatten()
    w = w.clamp(-1.0, 1.0)
    pcm = (w.numpy() * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    sf.write(buf, pcm, 24000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


async def asynthesize_pcm_bytes(
    text: str,
    settings: Settings,
    *,
    voice_ref_path: str | None = None,
) -> tuple[bytes, int]:
    """
    Async, backend-aware synthesis that returns raw PCM_S16LE bytes + sample rate.

    Called by ``/ws/voice`` and ``/tts`` — lets Edge TTS run natively async
    (no event-loop blocking) while OmniVoice keeps running on a worker thread.
    """
    import asyncio

    if active_backend(settings) == "edge":
        from app.services import tts_edge

        voice = voice_ref_path or settings.tts_edge_voice
        return await tts_edge.synthesize_pcm_bytes(
            text, voice=voice, speed=settings.tts_speed
        )

    # OmniVoice: heavy sync call — keep the event loop responsive.
    wave = await asyncio.to_thread(
        synthesize_to_tensor, text, settings, voice_ref_path=voice_ref_path
    )
    w = wave.detach().cpu().float().squeeze()
    if w.dim() != 1:
        w = w.flatten()
    w = w.clamp(-1.0, 1.0)
    pcm = (w.numpy() * 32767.0).astype(np.int16)
    return pcm.tobytes(), 24000


def pcm_bytes_to_chunks(pcm: bytes, chunk_samples: int) -> list[bytes]:
    """Slice raw 16-bit PCM byte-string into ``chunk_samples``-sized frames."""
    if chunk_samples <= 0:
        chunk_samples = 768
    step = chunk_samples * 2  # 2 bytes per int16 sample
    return [pcm[i : i + step] for i in range(0, len(pcm), step)]


def tensor_to_pcm_s16le_chunks(
    wave: torch.Tensor,
    sample_rate: int,
    chunk_samples: int,
) -> list[bytes]:
    """Slice (1, T) float tensor to int16 PCM chunks."""
    w = wave.detach().cpu().float().squeeze()
    if w.dim() != 1:
        w = w.flatten()
    w = w.clamp(-1.0, 1.0)
    pcm = (w.numpy() * 32767.0).astype(np.int16)
    if chunk_samples <= 0:
        chunk_samples = 768
    chunks: list[bytes] = []
    for i in range(0, len(pcm), chunk_samples):
        part = pcm[i : i + chunk_samples]
        chunks.append(part.tobytes())
    return chunks


# --- Sentence splitting for progressive TTS streaming -----------------------

# Uzbek + common ASCII sentence terminators. Keep ``…`` as a single unit.
_SENTENCE_END_RE = re.compile(r"([.!?\u2026]+)(?=\s|$)", re.UNICODE)
_SECONDARY_PAUSE_RE = re.compile(r"([,;:\u2014\u2013])(?=\s)", re.UNICODE)


def _coalesce_fragments(
    fragments: list[str], *, min_chars: int, max_chars: int
) -> list[str]:
    """Glue short neighbour fragments until each chunk is at least ``min_chars`` or
    the last remaining piece, while never growing past ``max_chars``."""
    out: list[str] = []
    buf = ""
    for frag in fragments:
        if not frag:
            continue
        if not buf:
            buf = frag
            continue
        joined_len = len(buf) + 1 + len(frag)
        if len(buf) < min_chars and joined_len <= max_chars:
            buf = f"{buf} {frag}".strip()
        else:
            out.append(buf)
            buf = frag
    if buf:
        if out and len(buf) < min_chars and (len(out[-1]) + 1 + len(buf)) <= max_chars:
            out[-1] = f"{out[-1]} {buf}".strip()
        else:
            out.append(buf)
    return out


def split_text_for_tts(
    text: str,
    *,
    min_chars: int = 40,
    max_chars: int = 220,
) -> list[str]:
    """
    Split ``text`` into TTS-friendly segments.

    Why: OmniVoice (flow-matching / diffusion) synthesizes the whole input in one
    call. For progressive streaming we want roughly sentence-sized chunks so the
    first audible word lands fast without making each chunk so short that prosody
    suffers.

    Rules:

    - Break on ``.``, ``!``, ``?``, ``…`` terminators.
    - If a resulting piece is still longer than ``max_chars``, sub-split on
      commas / semicolons / dashes.
    - Coalesce tiny neighbours so every yielded chunk is at least ``min_chars``
      (except possibly the final piece when the whole reply is shorter).
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    # Primary split on sentence terminators, keeping punctuation attached.
    primary: list[str] = []
    last = 0
    for m in _SENTENCE_END_RE.finditer(cleaned):
        end = m.end()
        piece = cleaned[last:end].strip()
        if piece:
            primary.append(piece)
        last = end
    tail = cleaned[last:].strip()
    if tail:
        primary.append(tail)
    if not primary:
        primary = [cleaned]

    # Sub-split oversized sentences on secondary pause points.
    secondary: list[str] = []
    for piece in primary:
        if len(piece) <= max_chars:
            secondary.append(piece)
            continue
        start = 0
        for m in _SECONDARY_PAUSE_RE.finditer(piece):
            end = m.end()
            chunk = piece[start:end].strip()
            if chunk:
                secondary.append(chunk)
            start = end
        rest = piece[start:].strip()
        if rest:
            secondary.append(rest)

    return _coalesce_fragments(secondary, min_chars=min_chars, max_chars=max_chars)


def iter_synthesize_segments(
    text: str,
    settings: Settings,
    *,
    voice_ref_path: str | None = None,
    min_chars: int | None = None,
    max_chars: int | None = None,
) -> Iterator[tuple[str, torch.Tensor]]:
    """
    Yield ``(segment_text, waveform)`` one at a time.

    Callers can push each ``waveform`` straight to the wire before requesting the
    next segment, giving the user "first-word" latency equal to the synthesis time
    of just the first sentence instead of the entire reply.
    """
    minc = int(min_chars if min_chars is not None else settings.tts_stream_min_chars)
    maxc = int(max_chars if max_chars is not None else settings.tts_stream_max_chars)
    segments = split_text_for_tts(text, min_chars=minc, max_chars=maxc)
    for seg in segments:
        wave = synthesize_to_tensor(seg, settings, voice_ref_path=voice_ref_path)
        yield seg, wave


def warmup(settings: Settings) -> None:
    """
    Force OmniVoice's lazy internal ASR (``whisper-large-v3-turbo``) to load now
    instead of during the first user-visible TTS call (which otherwise adds a
    cold-start hit of 20–30 s). Also materializes the reference-audio cache entry.

    Edge TTS is cloud-served and starts in ~1 s from idle; no warmup needed.
    """
    if active_backend(settings) == "edge":
        logger.info("TTS_BACKEND=edge: warmup skipped (cloud TTS, no cold start).")
        return
    if _model is None:
        logger.debug("TTS warmup skipped: model not initialized")
        return
    probe = (settings.tts_warmup_text or "").strip() or "Salom."
    try:
        synthesize_to_tensor(probe, settings)
        logger.info("TTS warmup complete (probe=%r)", probe)
    except Exception:
        logger.exception("TTS warmup failed (non-fatal; first call will pay the cost).")
