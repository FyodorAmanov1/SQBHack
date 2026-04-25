"""Unit tests for voice catalog display labels."""

from pathlib import Path

from app.services.voices import label_for_voice_path


def test_label_top_level():
    assert label_for_voice_path(Path("reference.wav")) == "reference"


def test_label_nested():
    assert label_for_voice_path(Path("north") / "clip.wav") == "north — clip"
