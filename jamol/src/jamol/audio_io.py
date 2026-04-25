"""Microphone capture and WAV playback (used with API STT/TTS)."""

from __future__ import annotations

import io
import logging
import queue
import threading
import time
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

# WebRTC VAD only accepts 8k/16k/32k/48k. 16 kHz matches Whisper's native rate.
_VAD_SAMPLE_RATES = (8000, 16000, 32000, 48000)
# 10/20/30 ms frames allowed; 30 ms gives the most reliable speech/silence classification.
_VAD_FRAME_MS = 30


def _sounddevice():
    try:
        import sounddevice as sd
    except ImportError as e:
        raise RuntimeError(
            "The 'sounddevice' package is required for the microphone and playback. "
            "Install it in the same environment you use for Jamol:\n"
            "  pip install sounddevice\n"
            "Or reinstall Jamol so dependencies match pyproject.toml:\n"
            "  pip install -e ./jamol"
        ) from e
    return sd


def _record_float32(*, max_seconds: float, sample_rate: int) -> "np.ndarray":
    """Shared mono float32 capture — raw numpy array at ``sample_rate`` Hz."""
    sd = _sounddevice()

    cap = float(min(max(max_seconds, 0.5), 120.0))
    frames = int(cap * sample_rate)
    logger.info("Recording %.1f s at %d Hz…", cap, sample_rate)
    recording = sd.rec(
        frames,
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        blocking=True,
    )
    if recording.size == 0:
        return np.zeros((0,), dtype=np.float32)
    wave = np.squeeze(recording)
    if wave.ndim > 1:
        wave = wave[:, 0]
    return wave.astype(np.float32, copy=False)


def record_wav_bytes(*, max_seconds: float, sample_rate: int = 16000) -> bytes:
    """Record mono float32 from default input device; return WAV bytes (16-bit PCM)."""
    import soundfile as sf

    wave = _record_float32(max_seconds=max_seconds, sample_rate=sample_rate)
    if wave.size == 0:
        return b""
    buf = io.BytesIO()
    sf.write(buf, wave, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def record_pcm_s16le(
    *,
    max_seconds: float,
    sample_rate: int = 16000,
) -> tuple[bytes, int]:
    """Record raw little-endian 16-bit PCM (no WAV header), ready for ``/ws/voice``."""
    wave = _record_float32(max_seconds=max_seconds, sample_rate=sample_rate)
    if wave.size == 0:
        return b"", sample_rate
    clipped = np.clip(wave, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    return pcm.tobytes(), sample_rate


def play_wav_bytes(wav_bytes: bytes) -> None:
    """Play WAV bytes on the default output device."""
    import io

    sd = _sounddevice()
    import soundfile as sf

    if not wav_bytes:
        return
    buf = io.BytesIO(wav_bytes)
    data, sr = sf.read(buf, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    sd.play(data, int(sr))
    sd.wait()


def play_wav_bytes_if_available(wav_bytes: bytes, *, enabled: bool = True) -> None:
    if not enabled or not wav_bytes:
        return
    try:
        play_wav_bytes(wav_bytes)
    except Exception as e:
        logger.warning("Playback failed: %s", e)


@dataclass(frozen=True)
class InputDevice:
    """A selectable mic device as returned by :func:`list_input_devices`."""

    index: int
    name: str
    hostapi_name: str
    is_default: bool

    @property
    def label(self) -> str:
        suffix = "  [default]" if self.is_default else ""
        return f"{self.name} — {self.hostapi_name}{suffix}"


def list_input_devices() -> list[InputDevice]:
    """Enumerate mic-capable devices. Empty list if sounddevice fails to load."""
    try:
        sd = _sounddevice()
    except RuntimeError:
        return []
    try:
        raw = sd.query_devices()
        apis = sd.query_hostapis()
        default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
    except Exception as e:  # noqa: BLE001 - sounddevice surfaces a variety of errors
        logger.warning("Could not enumerate input devices: %s", e)
        return []

    out: list[InputDevice] = []
    for i, d in enumerate(raw):
        if int(d.get("max_input_channels", 0)) <= 0:
            continue
        api_idx = int(d.get("hostapi", 0))
        api_name = apis[api_idx].get("name", "") if 0 <= api_idx < len(apis) else ""
        out.append(
            InputDevice(
                index=i,
                name=str(d.get("name", f"Device {i}")),
                hostapi_name=str(api_name),
                is_default=(i == default_in),
            )
        )
    return out


def _resolve_vad_sample_rate(sample_rate: int) -> int:
    """WebRTC VAD is strict about its sample rate; fall back to 16 kHz."""
    if sample_rate in _VAD_SAMPLE_RATES:
        return sample_rate
    logger.warning(
        "VAD sample rate %d not supported; using 16000 Hz.", sample_rate
    )
    return 16000


def record_pcm_streaming(
    *,
    stop_event: threading.Event | None = None,
    device: int | str | None = None,
    sample_rate: int = 16000,
    max_seconds: float = 15.0,
    vad_enabled: bool = True,
    vad_aggressiveness: int = 2,
    silence_tail_ms: int = 700,
    min_speech_ms: int = 200,
    preroll_ms: int = 200,
) -> tuple[bytes, int]:
    """
    Stream mic -> raw PCM s16le. Stops on the first of:

    - ``stop_event`` set (external manual stop, e.g. button release / hotkey up),
    - VAD: ``silence_tail_ms`` of trailing silence after speech was detected,
    - ``max_seconds`` elapsed.

    Returns ``(pcm_bytes, sample_rate)``. If VAD is enabled, leading silence is
    trimmed to a short pre-roll; otherwise the full capture is returned.
    """
    sd = _sounddevice()
    vad_sr = _resolve_vad_sample_rate(sample_rate)
    frame_samples = vad_sr * _VAD_FRAME_MS // 1000
    frame_bytes = frame_samples * 2

    vad = None
    if vad_enabled:
        try:
            import webrtcvad

            vad = webrtcvad.Vad(max(0, min(3, int(vad_aggressiveness))))
        except ImportError:
            logger.warning(
                "webrtcvad not installed; recording without silence endpointing. "
                "Install: pip install webrtcvad-wheels"
            )
            vad = None

    stop_event = stop_event or threading.Event()
    raw_q: queue.Queue[bytes] = queue.Queue()

    def _callback(indata, _frames, _time_info, status):  # noqa: ANN001 - sounddevice signature
        if status:
            logger.debug("Input stream status: %s", status)
        raw_q.put(bytes(indata))

    collected = bytearray()
    pre_buffer = bytearray()
    pre_buffer_max = max(frame_bytes, (preroll_ms // _VAD_FRAME_MS) * frame_bytes)
    min_speech_frames = max(1, min_speech_ms // _VAD_FRAME_MS)
    silence_tail_frames = max(1, silence_tail_ms // _VAD_FRAME_MS)

    speech_started = False
    voiced_run = 0
    trailing_silence = 0
    leftover = bytearray()
    start_ts = time.monotonic()

    stream = sd.RawInputStream(
        samplerate=vad_sr,
        blocksize=frame_samples,
        channels=1,
        dtype="int16",
        device=device,
        callback=_callback,
    )
    try:
        stream.start()
    except Exception as e:
        raise RuntimeError(
            f"Could not open input device {device!r}: {e}. "
            "Check Windows microphone permissions and try another device."
        ) from e

    try:
        while True:
            if stop_event.is_set():
                break
            if (time.monotonic() - start_ts) > max_seconds:
                logger.debug("VAD recording hit max_seconds cap.")
                break
            try:
                chunk = raw_q.get(timeout=0.1)
            except queue.Empty:
                continue

            leftover.extend(chunk)
            while len(leftover) >= frame_bytes:
                frame = bytes(leftover[:frame_bytes])
                del leftover[:frame_bytes]

                if vad is None:
                    collected.extend(frame)
                    continue

                is_speech = vad.is_speech(frame, vad_sr)
                if not speech_started:
                    pre_buffer.extend(frame)
                    if len(pre_buffer) > pre_buffer_max:
                        del pre_buffer[: len(pre_buffer) - pre_buffer_max]
                    if is_speech:
                        voiced_run += 1
                        if voiced_run >= min_speech_frames:
                            speech_started = True
                            collected.extend(pre_buffer)
                            pre_buffer.clear()
                            trailing_silence = 0
                    else:
                        voiced_run = 0
                else:
                    collected.extend(frame)
                    if is_speech:
                        trailing_silence = 0
                    else:
                        trailing_silence += 1
                        if trailing_silence >= silence_tail_frames:
                            stop_event.set()
                            break
    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            logger.debug("Error closing input stream", exc_info=True)

    if vad is not None and not speech_started:
        return b"", vad_sr
    return bytes(collected), vad_sr
