from __future__ import annotations

import logging
import os
import tempfile
import threading
from typing import Any, Literal

import speech_recognition as sr

logger = logging.getLogger(__name__)

EngineName = Literal["google", "whisper", "backend"]

_whisper_model_cache: dict[tuple[str, str, str], Any] = {}


def build_recognizer() -> sr.Recognizer:
    r = sr.Recognizer()
    r.dynamic_energy_threshold = True
    return r


def listen_once_microphone(
    recognizer: sr.Recognizer,
    *,
    timeout: float,
    phrase_time_limit: float | None,
) -> sr.AudioData:
    try:
        import pyaudio  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "PyAudio is not installed. For microphone input: "
            "pip install 'jamol[voice]' (or a PyAudio wheel for your Python version; "
            "see jamol/README.md)."
        ) from e

    try:
        with sr.Microphone() as source:
            logger.debug("Calibrating for ambient noise…")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            logger.info("Listening…")
            return recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=phrase_time_limit,
            )
    except OSError as e:
        raise RuntimeError(
            "Could not open the microphone. Check PyAudio install and Windows mic permissions."
        ) from e


def transcribe_google(recognizer: sr.Recognizer, audio: sr.AudioData) -> str:
    text = recognizer.recognize_google(audio, language="en-US")
    return text.strip()


def _get_whisper_model(model_size: str, device: str, compute_type: str) -> Any:
    global _whisper_model_cache
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "Whisper engine requires optional deps: "
            "pip install '.[whisper]' from the jamol folder "
            "(faster-whisper, soundfile, numpy)."
        ) from e

    key = (model_size, device, compute_type)
    if key not in _whisper_model_cache:
        logger.info(
            "Loading faster-whisper model %s (device=%s)…",
            model_size,
            device,
        )
        _whisper_model_cache[key] = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
    return _whisper_model_cache[key]


def transcribe_whisper(
    audio: sr.AudioData,
    *,
    model_size: str = "base",
    device: str = "cpu",
    compute_type: str = "int8",
) -> str:
    model = _get_whisper_model(model_size, device, compute_type)
    wav_bytes = audio.get_wav_data()
    path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        with open(path, "wb") as f:
            f.write(wav_bytes)
        segments, _info = model.transcribe(
            path,
            language="uz",
            task="transcribe",
        )
        parts: list[str] = []
        for seg in segments:
            t = (seg.text or "").strip()
            if t:
                parts.append(t)
        text = " ".join(parts).strip()
        if not text:
            segments_en, _ = model.transcribe(path, language="en", task="transcribe")
            for seg in segments_en:
                t = (seg.text or "").strip()
                if t:
                    parts.append(t)
            text = " ".join(parts).strip()
        return text
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def capture_pcm(
    *,
    max_seconds: float,
    stop_event: threading.Event | None = None,
    device: int | str | None = None,
    vad_enabled: bool = True,
    sample_rate: int = 16000,
) -> tuple[bytes, int]:
    """
    Capture mic audio with VAD endpointing when ``vad_enabled``; else the legacy
    fixed-duration recorder. Returns ``(pcm_s16le, sample_rate)``.
    """
    if vad_enabled or stop_event is not None:
        from jamol.audio_io import record_pcm_streaming

        return record_pcm_streaming(
            stop_event=stop_event,
            device=device,
            sample_rate=sample_rate,
            max_seconds=max_seconds,
            vad_enabled=vad_enabled,
        )

    from jamol.audio_io import record_pcm_s16le

    return record_pcm_s16le(max_seconds=max_seconds, sample_rate=sample_rate)


def transcribe_pcm_via_api(
    pcm: bytes,
    sample_rate: int,
    *,
    api_client: Any,
) -> str:
    """Send PCM to the server: WebSocket (``stt_only``) with POST /stt fallback."""
    if not pcm:
        return ""
    try:
        return api_client.stt_via_ws(pcm, sample_rate=sample_rate)
    except Exception as ws_err:  # noqa: BLE001
        logger.warning(
            "WebSocket STT failed (%s); falling back to POST /stt", ws_err
        )
        import io

        import numpy as np
        import soundfile as sf

        samples = np.frombuffer(pcm, dtype=np.int16)
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
        return api_client.stt_upload_wav(buf.getvalue())


def listen_and_transcribe(
    *,
    engine: EngineName,
    timeout: float = 8.0,
    phrase_time_limit: float | None = 12.0,
    whisper_model: str = "base",
    whisper_device: str = "cpu",
    whisper_compute_type: str = "int8",
    backend_settings: Any | None = None,
    api_client: Any | None = None,
    stop_event: threading.Event | None = None,
    device_index: int | None = None,
    vad_enabled: bool = True,
) -> str | None:
    """
    Capture one utterance from the default microphone and return text, or None on failure.
    If ``api_client`` is set, audio is sent to ``/ws/voice`` (stt_only) with a
    ``POST /stt`` fallback — same pipeline as the browser client.
    ``engine=backend`` uses in-process ``app.services.stt`` when API is not used.
    """
    if api_client is not None:
        cap = phrase_time_limit if phrase_time_limit is not None else 15.0
        pcm, sr = capture_pcm(
            max_seconds=cap,
            stop_event=stop_event,
            device=device_index,
            vad_enabled=vad_enabled,
        )
        if not pcm:
            return None
        text = transcribe_pcm_via_api(pcm, sr, api_client=api_client)
        return text if text else None

    if engine == "backend":
        try:
            from jamol.backend_rtv import (
                load_backend_settings,
                transcribe_pcm_embedded,
            )
        except ImportError as e:
            raise RuntimeError(
                "Backend STT requires the RealTimeVoice backend on PYTHONPATH and "
                "optional deps: pip install 'jamol[backend]' (see jamol/README.md)."
            ) from e
        settings = backend_settings if backend_settings is not None else load_backend_settings()
        cap = phrase_time_limit if phrase_time_limit is not None else 15.0
        pcm, sr = capture_pcm(
            max_seconds=cap,
            stop_event=stop_event,
            device=device_index,
            vad_enabled=vad_enabled,
        )
        if not pcm:
            return None
        text = transcribe_pcm_embedded(pcm, sr, settings)
        return text if text else None

    recognizer = build_recognizer()
    try:
        audio = listen_once_microphone(
            recognizer,
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
        )
    except sr.WaitTimeoutError:
        logger.warning("No speech detected before timeout.")
        return None
    except OSError as e:
        logger.error("Microphone error: %s", e)
        return None

    try:
        if engine == "google":
            return transcribe_google(recognizer, audio)
        if engine == "whisper":
            return transcribe_whisper(
                audio,
                model_size=whisper_model,
                device=whisper_device,
                compute_type=whisper_compute_type,
            )
    except sr.UnknownValueError:
        logger.warning("Could not understand audio.")
        return None
    except sr.RequestError as e:
        logger.error("Speech recognition service error: %s", e)
        return None

    raise ValueError(f"Unknown engine: {engine}")
