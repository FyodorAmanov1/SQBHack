"""Unit tests for :mod:`app.services.tts_edge` (Edge TTS backend)."""

from __future__ import annotations

import asyncio

import pytest

from app.services import tts_edge


@pytest.mark.parametrize(
    "speed, expected",
    [
        (1.0, "+0%"),
        (1.1, "+10%"),
        (1.25, "+25%"),
        (0.9, "-10%"),
        (0.5, "-50%"),
        (3.0, "+100%"),  # clamped
        (0.1, "-50%"),  # clamped
        ("bad", "+0%"),  # type-safe fallback
        (None, "+0%"),
    ],
)
def test_rate_string_from_speed(speed, expected) -> None:
    assert tts_edge.rate_string_from_speed(speed) == expected


def test_uzbek_voice_ids_present() -> None:
    """Both Microsoft Uzbek voices must be exposed."""
    ids = tts_edge.uzbek_voice_ids()
    assert "uz-UZ-MadinaNeural" in ids
    assert "uz-UZ-SardorNeural" in ids
    assert len(ids) == 2


def test_resolve_voice_defaults_for_empty_and_none() -> None:
    assert tts_edge.resolve_voice(None) == tts_edge.DEFAULT_UZ_VOICE
    assert tts_edge.resolve_voice("") == tts_edge.DEFAULT_UZ_VOICE
    assert tts_edge.resolve_voice("   ") == tts_edge.DEFAULT_UZ_VOICE


def test_resolve_voice_recognizes_short_aliases() -> None:
    assert tts_edge.resolve_voice("madina") == "uz-UZ-MadinaNeural"
    assert tts_edge.resolve_voice("MADINA") == "uz-UZ-MadinaNeural"
    assert tts_edge.resolve_voice("sardor") == "uz-UZ-SardorNeural"
    assert tts_edge.resolve_voice("ayol") == "uz-UZ-MadinaNeural"
    assert tts_edge.resolve_voice("erkak") == "uz-UZ-SardorNeural"


def test_resolve_voice_accepts_exact_id() -> None:
    assert tts_edge.resolve_voice("uz-UZ-SardorNeural") == "uz-UZ-SardorNeural"


def test_resolve_voice_passes_through_foreign_locale() -> None:
    """Unknown locales like en-US-* should be forwarded unchanged (Edge validates server-side)."""
    assert tts_edge.resolve_voice("en-US-AriaNeural") == "en-US-AriaNeural"


def test_decode_mp3_to_pcm_empty_input() -> None:
    assert tts_edge._decode_mp3_to_pcm(b"") == b""


def test_synthesize_pcm_bytes_empty_text() -> None:
    """Empty / whitespace input must short-circuit before hitting the network."""
    pcm, sr = asyncio.run(
        tts_edge.synthesize_pcm_bytes("   ", voice="uz-UZ-MadinaNeural")
    )
    assert pcm == b""
    assert sr == tts_edge.EDGE_SAMPLE_RATE
