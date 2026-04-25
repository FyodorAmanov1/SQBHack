"""Unit tests for mic device enumeration and VAD frame parameters (no hardware)."""

from __future__ import annotations

import pytest

from jamol.audio_io import (
    _VAD_FRAME_MS,
    _VAD_SAMPLE_RATES,
    InputDevice,
    _resolve_vad_sample_rate,
    list_input_devices,
)


def test_vad_frame_constants_match_webrtc_spec() -> None:
    """WebRTC VAD supports 8k/16k/32k/48k sample rates and 10/20/30 ms frames."""
    assert _VAD_SAMPLE_RATES == (8000, 16000, 32000, 48000)
    assert _VAD_FRAME_MS in (10, 20, 30)


@pytest.mark.parametrize(
    "given, expected",
    [(16000, 16000), (48000, 48000), (44100, 16000), (22050, 16000), (0, 16000)],
)
def test_resolve_vad_sample_rate_falls_back_to_16k(given: int, expected: int) -> None:
    assert _resolve_vad_sample_rate(given) == expected


def test_list_input_devices_is_safe_without_hardware(monkeypatch: pytest.MonkeyPatch) -> None:
    """If sounddevice raises while enumerating, we must return [] and not crash."""
    import jamol.audio_io as aio

    class _FakeSd:
        class default:
            device = (0, 0)

        @staticmethod
        def query_devices():
            raise RuntimeError("no host api")

        @staticmethod
        def query_hostapis():
            return []

    monkeypatch.setattr(aio, "_sounddevice", lambda: _FakeSd)
    assert list_input_devices() == []


def test_list_input_devices_builds_dataclasses(monkeypatch: pytest.MonkeyPatch) -> None:
    import jamol.audio_io as aio

    class _FakeSd:
        class default:
            device = (1, 0)

        @staticmethod
        def query_devices():
            return [
                {"name": "Speakers", "max_input_channels": 0, "hostapi": 0},
                {"name": "Mic A", "max_input_channels": 1, "hostapi": 0},
                {"name": "Mic B", "max_input_channels": 2, "hostapi": 1},
            ]

        @staticmethod
        def query_hostapis():
            return [{"name": "MME"}, {"name": "WASAPI"}]

    monkeypatch.setattr(aio, "_sounddevice", lambda: _FakeSd)
    devs = list_input_devices()
    assert len(devs) == 2
    a, b = devs
    assert isinstance(a, InputDevice)
    assert a.name == "Mic A" and a.hostapi_name == "MME" and a.is_default is True
    assert b.name == "Mic B" and b.hostapi_name == "WASAPI" and b.is_default is False
    assert "[default]" in a.label and "[default]" not in b.label
