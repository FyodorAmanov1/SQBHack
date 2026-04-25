from __future__ import annotations

from jamol.config import AppEntry, OpenSpec
from jamol.intents import match_intent, normalize


def _sample_apps() -> list[AppEntry]:
    return [
        AppEntry(
            id="notepad",
            phrases=("open notepad", "notepad och"),
            open=OpenSpec(kind="shell_execute", target="notepad"),
        ),
        AppEntry(
            id="calculator",
            phrases=("open calculator", "kalkulyatorni och"),
            open=OpenSpec(kind="shell_execute", target="calc"),
        ),
    ]


def test_normalize_basic() -> None:
    assert normalize("  Open NOTEPAD!  ") == "open notepad"


def test_match_longest_phrase() -> None:
    apps = _sample_apps()
    assert match_intent("please open notepad now", apps) == "notepad"
    assert match_intent("kalkulyatorni och", apps) == "calculator"


def test_match_none() -> None:
    assert match_intent("random words", _sample_apps()) is None
