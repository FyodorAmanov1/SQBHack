from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

_model = None

# Official faster-whisper sizes (accepted as-is by WhisperModel without conversion).
_OFFICIAL_WHISPER_SIZES = frozenset(
    {
        "tiny",
        "tiny.en",
        "base",
        "base.en",
        "small",
        "small.en",
        "medium",
        "medium.en",
        "large-v1",
        "large-v2",
        "large-v3",
        "large",
        "distil-small.en",
        "distil-medium.en",
        "distil-large-v2",
        "distil-large-v3",
    }
)

# Files commonly emitted by Whisper fine-tunes that faster-whisper/ctranslate2 needs
# alongside the CT2 ``model.bin``. Missing files are silently skipped.
_WHISPER_COPY_FILES = (
    "tokenizer.json",
    "preprocessor_config.json",
    "vocabulary.txt",
    "vocabulary.json",
    "vocab.json",
    "merges.txt",
    "normalizer.json",
    "added_tokens.json",
    "special_tokens_map.json",
    "generation_config.json",
    "tokenizer_config.json",
)


def _resolve_device(settings: Settings) -> str:
    d = (settings.stt_device or "auto").lower()
    if d == "auto":
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"
    return d


def _resolve_compute_type(settings: Settings, device: str) -> str:
    ct = settings.stt_compute_type
    if ct and ct != "default":
        return ct
    if device == "cuda":
        return "float16"
    return "int8"


def _backend_root() -> Path:
    """``backend/`` directory (same anchor ``config.py`` uses for .env)."""
    return Path(__file__).resolve().parents[2]


def _cache_root(settings: Settings) -> Path:
    raw = (settings.stt_model_cache_dir or "models/whisper_ct2").strip()
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = _backend_root() / p
    return p


def _is_ct2_dir(path: Path) -> bool:
    return path.is_dir() and (path / "model.bin").is_file()


def _safe_repo_dirname(repo_id: str) -> str:
    return repo_id.strip().replace("\\", "/").replace("/", "__")


def _convert_hf_whisper_to_ct2(
    repo_id: str,
    target_dir: Path,
    *,
    quantization: str,
) -> Path:
    """Download ``repo_id`` from HF and convert to a CT2 checkpoint at ``target_dir``."""
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists() and not _is_ct2_dir(target_dir):
        # Partial/failed previous run — clean up before retrying.
        logger.warning("Removing incomplete CT2 cache at %s", target_dir)
        shutil.rmtree(target_dir, ignore_errors=True)
    if _is_ct2_dir(target_dir):
        return target_dir

    try:
        from ctranslate2.converters import TransformersConverter
    except ImportError as e:
        raise RuntimeError(
            "HF Whisper auto-conversion needs ctranslate2 (bundled with faster-whisper). "
            "Reinstall: pip install --upgrade faster-whisper"
        ) from e

    logger.info(
        "Converting HF Whisper %r -> CT2 (%s) at %s",
        repo_id,
        quantization,
        target_dir,
    )
    converter = TransformersConverter(
        repo_id,
        copy_files=list(_WHISPER_COPY_FILES),
        load_as_float16=(quantization in {"float16", "int8_float16"}),
    )
    converter.convert(
        str(target_dir),
        quantization=quantization,
        force=True,
    )
    if not _is_ct2_dir(target_dir):
        raise RuntimeError(
            f"CT2 conversion finished but {target_dir / 'model.bin'} is missing."
        )
    return target_dir


def _resolve_whisper_model(settings: Settings) -> str:
    """
    Turn ``stt_model_size`` into something :class:`faster_whisper.WhisperModel` accepts.

    Three cases:

    - Official whisper size (``"large-v3"``, ``"small"`` …) -> pass through unchanged
      (faster-whisper downloads the Systran CT2 mirror itself).
    - Local directory (already CT2-converted) -> absolute path string.
    - Hugging Face repo id (``"islomov/rubaistt_v2_medium"``) -> downloaded + converted
      to a cached CT2 directory on first use.
    """
    raw = (settings.stt_model_size or "small").strip()
    if not raw:
        return "small"

    if raw in _OFFICIAL_WHISPER_SIZES:
        return raw

    p = Path(raw).expanduser()
    if p.is_absolute() or raw.startswith((".", "/", "\\")) or p.exists():
        abs_path = p if p.is_absolute() else (_backend_root() / p).resolve()
        if _is_ct2_dir(abs_path):
            return str(abs_path)
        raise RuntimeError(
            f"STT_MODEL_SIZE points to {abs_path}, but it is not a CT2 model dir "
            "(missing model.bin). Re-convert with ct2-transformers-converter."
        )

    if "/" in raw:
        cache_root = _cache_root(settings)
        target = cache_root / _safe_repo_dirname(raw)
        if _is_ct2_dir(target):
            return str(target.resolve())
        quantization = (settings.stt_ct2_quantization or "float16").strip() or "float16"
        converted = _convert_hf_whisper_to_ct2(
            raw, target, quantization=quantization
        )
        return str(converted.resolve())

    # Fallback: hand the raw value to faster-whisper and let it try.
    return raw


def init_model(settings: Settings) -> None:
    global _model
    if _model is not None:
        return
    from faster_whisper import WhisperModel

    device = _resolve_device(settings)
    compute_type = _resolve_compute_type(settings, device)
    resolved = _resolve_whisper_model(settings)
    if resolved != settings.stt_model_size:
        logger.info(
            "STT_MODEL_SIZE=%s resolved to %s", settings.stt_model_size, resolved
        )
    logger.info(
        "Loading Whisper model=%s device=%s compute_type=%s",
        resolved,
        device,
        compute_type,
    )
    _model = WhisperModel(
        resolved,
        device=device,
        compute_type=compute_type,
    )


def _transcribe_kwargs(settings: Settings) -> dict[str, Any]:
    """Keyword arguments for faster_whisper.WhisperModel.transcribe."""
    lang = (settings.stt_language or "").strip() or None
    kw: dict[str, Any] = {
        "task": "transcribe",
        "language": lang,
        "vad_filter": settings.stt_vad_filter,
        "beam_size": max(1, settings.stt_beam_size),
        "best_of": max(1, settings.stt_best_of),
        "without_timestamps": settings.stt_without_timestamps,
        "condition_on_previous_text": settings.stt_condition_on_previous_text,
        "patience": float(settings.stt_patience),
        "repetition_penalty": float(settings.stt_repetition_penalty),
        "no_repeat_ngram_size": max(0, int(settings.stt_no_repeat_ngram_size)),
        "compression_ratio_threshold": float(settings.stt_compression_ratio_threshold),
    }
    prompt = (settings.stt_initial_prompt or "").strip()
    if prompt:
        kw["initial_prompt"] = prompt
    hot = (settings.stt_hotwords or "").strip()
    if hot:
        kw["hotwords"] = hot

    raw = (settings.stt_vad_parameters_json or "").strip()
    if raw:
        try:
            vp = json.loads(raw)
            if isinstance(vp, dict):
                kw["vad_parameters"] = vp
            else:
                logger.warning(
                    "STT_VAD_PARAMETERS_JSON must be a JSON object, got %s; ignoring.",
                    type(vp).__name__,
                )
        except json.JSONDecodeError as e:
            logger.warning("STT_VAD_PARAMETERS_JSON parse error: %s", e)

    if settings.stt_temperature is not None:
        kw["temperature"] = settings.stt_temperature
    if settings.stt_log_prob_threshold is not None:
        kw["log_prob_threshold"] = settings.stt_log_prob_threshold

    return kw


def _transcribe_audio_16k_mono(audio_16k: np.ndarray, settings: Settings) -> str:
    if _model is None:
        raise RuntimeError("STT model not initialized")
    segments, _info = _model.transcribe(audio_16k, **_transcribe_kwargs(settings))
    parts: list[str] = []
    for seg in segments:
        parts.append(seg.text.strip())
    return " ".join(p for p in parts if p).strip()


def _to_whisper_16k_mono(audio_f32: np.ndarray, sample_rate: int) -> np.ndarray:
    """Whisper expects 16 kHz mono float32."""
    import torch
    import torchaudio

    if audio_f32.size == 0:
        return audio_f32
    t = torch.from_numpy(audio_f32.astype(np.float32)).unsqueeze(0)
    if sample_rate != 16000:
        t = torchaudio.functional.resample(t, sample_rate, 16000)
    return t.squeeze(0).numpy()


def transcribe_pcm(pcm_s16le: bytes, sample_rate: int, settings: Settings) -> str:
    if _model is None:
        raise RuntimeError("STT model not initialized")
    if sample_rate <= 0:
        raise ValueError("Invalid sample rate")
    audio_i16 = np.frombuffer(pcm_s16le, dtype=np.int16)
    if audio_i16.size == 0:
        return ""
    audio_f32 = audio_i16.astype(np.float32) / 32768.0
    audio_16k = _to_whisper_16k_mono(audio_f32, sample_rate)
    return _transcribe_audio_16k_mono(audio_16k, settings)


def transcribe_file(path: Path, settings: Settings) -> str:
    import soundfile as sf

    if _model is None:
        raise RuntimeError("STT model not initialized")
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data_16k = _to_whisper_16k_mono(data, int(sr))
    return _transcribe_audio_16k_mono(data_16k, settings)
