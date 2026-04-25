"""Tests for :func:`app.services.tts.split_text_for_tts` (sentence streaming splitter)."""

from __future__ import annotations

import pytest

from app.services.tts import split_text_for_tts


def test_empty_returns_empty() -> None:
    assert split_text_for_tts("") == []
    assert split_text_for_tts("   ") == []


def test_single_short_reply_is_one_segment() -> None:
    # Shorter than min_chars, but it's the only content, so it must still be yielded.
    assert split_text_for_tts("Salom.") == ["Salom."]


def test_splits_on_sentence_terminators() -> None:
    text = (
        "Bugun havo yaxshi va quyoshli. "
        "Ertaga yomg‘ir yog‘ishi mumkin, shuning uchun soyabon oling. "
        "Iltimos, soyabon va salqin ichimlik oling sizga kerak bo‘ladi!"
    )
    segs = split_text_for_tts(text, min_chars=20, max_chars=220)
    assert len(segs) == 3
    assert segs[0].endswith(".")
    assert segs[1].endswith(".")
    assert segs[2].endswith("!")
    for seg in segs:
        assert seg == seg.strip()


def test_trailing_short_sentence_is_coalesced_into_previous() -> None:
    """Tiny tail ("Rahmat!") below min_chars must glue to its neighbour to avoid
    a near-empty audio segment with jittery prosody."""
    text = "Bugun havo juda yaxshi va quyoshli ochiq havoda. Rahmat!"
    segs = split_text_for_tts(text, min_chars=20, max_chars=220)
    assert len(segs) == 1
    assert "Rahmat!" in segs[0]


def test_coalesces_short_sentences_until_min_chars() -> None:
    text = "Ha. Yo‘q. Mayli. Bugun havo juda yaxshi va issiq, quyosh chiqqan."
    segs = split_text_for_tts(text, min_chars=40, max_chars=220)
    assert all(len(s) >= 10 for s in segs)
    assert segs[0].startswith("Ha.")
    assert "juda yaxshi" in " ".join(segs)


def test_secondary_split_for_long_sentences_without_periods() -> None:
    long_clause = (
        "birinchidan men bugun ishga bordim, keyin do‘stim bilan uchrashdim, "
        "so‘ngra kitob o‘qidim va uyga qaytdim va oilam bilan kechki ovqat qildik"
    )
    segs = split_text_for_tts(long_clause, min_chars=30, max_chars=80)
    assert len(segs) >= 2
    for s in segs:
        assert len(s) <= 80 + 8  # small slack for tail coalescing


def test_preserves_ellipsis_as_terminator() -> None:
    text = "Nimadir dedi… Keyin jim bo‘ldi. Ajab."
    segs = split_text_for_tts(text, min_chars=10, max_chars=220)
    assert segs[0].endswith("\u2026") or segs[0].endswith("...")
    assert any(s.endswith(".") for s in segs)


def test_idempotent_on_single_sentence_at_max() -> None:
    text = "A" * 200 + "."
    segs = split_text_for_tts(text, min_chars=40, max_chars=220)
    assert segs == [text]


@pytest.mark.parametrize(
    "text",
    [
        "Salom. Qalaysiz?",
        "Test. Test. Test. Test. Test.",
        "Just one line without terminator",
    ],
)
def test_joined_text_is_a_permutation_of_original_content(text: str) -> None:
    """Splitting must not silently drop words or mangle punctuation order."""
    segs = split_text_for_tts(text, min_chars=5, max_chars=400)
    joined = " ".join(segs)
    # Word sets should match (order preserved; punctuation may shift by whitespace).
    assert [w for w in joined.split() if w] == [w for w in text.split() if w]
