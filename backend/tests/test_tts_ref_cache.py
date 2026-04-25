"""The reference audio cache must read each WAV at most once per (path, mtime)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.services import tts as tts_mod


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    tts_mod.clear_ref_cache()
    yield
    tts_mod.clear_ref_cache()


def _write_silence_wav(path: Path, seconds: float = 0.1, sr: int = 16000) -> None:
    samples = np.zeros(int(seconds * sr), dtype=np.int16)
    sf.write(path, samples, sr, format="WAV", subtype="PCM_16")


def test_repeated_calls_hit_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav_path = tmp_path / "ref.wav"
    _write_silence_wav(wav_path)

    real_loader = tts_mod._load_ref_waveform_uncached
    calls: list[str] = []

    def _tracking(path: str):
        calls.append(path)
        return real_loader(path)

    monkeypatch.setattr(tts_mod, "_load_ref_waveform_uncached", _tracking)

    first = tts_mod._ref_audio_waveform_tuple(str(wav_path))
    second = tts_mod._ref_audio_waveform_tuple(str(wav_path))
    third = tts_mod._ref_audio_waveform_tuple(str(wav_path))

    assert len(calls) == 1, "soundfile must only open the reference WAV once"
    assert tts_mod.ref_cache_hits() == 2
    # Cached tensor is reused (identity), not re-decoded.
    assert first[0] is second[0]
    assert second[0] is third[0]


def test_cache_invalidates_when_file_mtime_changes(tmp_path: Path) -> None:
    wav_path = tmp_path / "ref.wav"
    _write_silence_wav(wav_path, seconds=0.1)
    first, _ = tts_mod._ref_audio_waveform_tuple(str(wav_path))

    # Overwrite with a different waveform and bump mtime.
    _write_silence_wav(wav_path, seconds=0.2)
    # Force a new mtime that clearly differs from the cached key.
    import os

    new_mtime = wav_path.stat().st_mtime + 5.0
    os.utime(wav_path, (new_mtime, new_mtime))

    second, _ = tts_mod._ref_audio_waveform_tuple(str(wav_path))
    assert second.shape != first.shape, (
        "Re-encoded file must produce a fresh tensor, not the stale cached one"
    )


def test_clear_ref_cache_resets_hit_counter(tmp_path: Path) -> None:
    wav_path = tmp_path / "ref.wav"
    _write_silence_wav(wav_path)
    tts_mod._ref_audio_waveform_tuple(str(wav_path))
    tts_mod._ref_audio_waveform_tuple(str(wav_path))
    assert tts_mod.ref_cache_hits() >= 1
    tts_mod.clear_ref_cache()
    assert tts_mod.ref_cache_hits() == 0
