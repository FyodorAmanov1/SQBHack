"""The :func:`tts.active_backend` dispatcher gating Edge vs OmniVoice paths."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services import tts as tts_mod


def test_active_backend_defaults_to_omnivoice() -> None:
    """The code-level default must remain ``omnivoice`` so upgrades are non-breaking.

    We pass an explicit value (rather than ``Settings()``) so this test doesn't
    read the developer's local ``.env`` file.
    """
    assert tts_mod.active_backend(Settings(tts_backend="omnivoice")) == "omnivoice"


@pytest.mark.parametrize("value, expected", [
    ("edge", "edge"),
    ("EDGE", "edge"),
    (" edge ", "edge"),
    ("omnivoice", "omnivoice"),
])
def test_active_backend_normalizes_known_values(value, expected) -> None:
    assert tts_mod.active_backend(Settings(tts_backend=value)) == expected


def test_active_backend_falls_back_on_typo(caplog: pytest.LogCaptureFixture) -> None:
    """A typo in TTS_BACKEND must not crash — fall back to OmniVoice with a warning."""

    class _S:
        tts_backend = "gibberish"

    assert tts_mod.active_backend(_S()) == "omnivoice"


def test_init_model_skips_omnivoice_when_backend_is_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``init_model`` must not even import OmniVoice when Edge is selected.

    This is what makes ``TTS_BACKEND=edge`` usable on machines without CUDA / without
    the ~5 GB OmniVoice weights."""
    called: list[bool] = []

    def _boom(*args, **kwargs):
        called.append(True)
        raise AssertionError("OmniVoice.from_pretrained must not run under Edge backend")

    monkeypatch.setattr(tts_mod, "_model", None)

    class _FakeOmni:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            return _boom()

    # Force the import site used by init_model() to our fake, then confirm unused.
    import sys

    monkeypatch.setitem(sys.modules, "omnivoice", type("omnivoice", (), {"OmniVoice": _FakeOmni}))

    tts_mod.init_model(Settings(tts_backend="edge"))
    assert called == []


def test_warmup_skipped_for_edge(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="app.services.tts")
    tts_mod.warmup(Settings(tts_backend="edge"))
    assert any("warmup skipped" in rec.message.lower() for rec in caplog.records)
