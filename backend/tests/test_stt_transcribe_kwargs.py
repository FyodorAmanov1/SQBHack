"""Smoke tests for STT transcribe keyword builder."""

import json

import pytest

from app.config import Settings
from app.services.stt import _transcribe_kwargs


def test_transcribe_kwargs_defaults():
    s = Settings()
    kw = _transcribe_kwargs(s)
    assert kw["task"] == "transcribe"
    assert kw["language"] == "uz"
    assert kw["vad_filter"] is True
    assert kw["beam_size"] == 7
    assert kw["condition_on_previous_text"] is False
    assert kw["patience"] == pytest.approx(1.15)
    assert kw["compression_ratio_threshold"] == pytest.approx(2.2)
    assert kw["no_repeat_ngram_size"] == 3
    assert "hotwords" in kw
    assert "haqiqiy" in kw["hotwords"]
    assert "initial_prompt" in kw
    assert "Toshkent" in kw["initial_prompt"]
    assert "Haqiqiy" in kw["initial_prompt"]


def test_transcribe_kwargs_initial_prompt():
    s = Settings(stt_initial_prompt="  Salom  ")
    kw = _transcribe_kwargs(s)
    assert kw["initial_prompt"] == "Salom"


def test_transcribe_kwargs_empty_language_and_prompt():
    s = Settings(stt_language="", stt_initial_prompt="", stt_hotwords="")
    kw = _transcribe_kwargs(s)
    assert kw["language"] is None
    assert "initial_prompt" not in kw
    assert "hotwords" not in kw


def test_transcribe_kwargs_empty_hotwords_omitted():
    s = Settings(stt_hotwords="   ")
    kw = _transcribe_kwargs(s)
    assert "hotwords" not in kw


def test_transcribe_kwargs_vad_json():
    s = Settings(stt_vad_parameters_json=json.dumps({"min_silence_duration_ms": 500}))
    kw = _transcribe_kwargs(s)
    assert kw["vad_parameters"] == {"min_silence_duration_ms": 500}


@pytest.mark.parametrize("temp", (0.0, 0.8))
def test_transcribe_kwargs_temperature(temp: float):
    s = Settings(stt_temperature=temp)
    kw = _transcribe_kwargs(s)
    assert kw["temperature"] == temp
