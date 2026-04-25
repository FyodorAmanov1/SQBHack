"""Hotkey module: graceful no-op when ``keyboard`` is missing, debounced press/release."""

from __future__ import annotations

import sys

import pytest

import jamol.hotkey as hk_mod
from jamol.hotkey import PushToTalkHotkey


def test_start_returns_false_without_keyboard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hk_mod, "_import_keyboard", lambda: None)
    hk = PushToTalkHotkey("f9", on_press=lambda: None, on_release=lambda: None)
    assert hk.start() is False
    hk.stop()


def _install_fake_keyboard(monkeypatch: pytest.MonkeyPatch) -> "FakeKeyboard":
    class _Evt:
        def __init__(self, name: str, etype: str) -> None:
            self.name = name
            self.event_type = etype

    class FakeKeyboard:
        KEY_DOWN = "down"
        KEY_UP = "up"

        def __init__(self) -> None:
            self._cb = None
            self.unhook_calls = 0

        def hook(self, cb):
            self._cb = cb
            return object()

        def unhook(self, _handle) -> None:
            self.unhook_calls += 1
            self._cb = None

        def fire(self, name: str, etype: str) -> None:
            if self._cb is not None:
                self._cb(_Evt(name, etype))

    fake = FakeKeyboard()
    monkeypatch.setattr(hk_mod, "_import_keyboard", lambda: fake)
    return fake


def test_press_and_release_are_debounced(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_keyboard(monkeypatch)
    presses: list[int] = []
    releases: list[int] = []

    hk = PushToTalkHotkey(
        "F9",
        on_press=lambda: presses.append(1),
        on_release=lambda: releases.append(1),
    )
    assert hk.start() is True

    fake.fire("f9", "down")
    fake.fire("f9", "down")
    fake.fire("f9", "up")
    fake.fire("f9", "up")

    assert presses == [1]
    assert releases == [1]

    fake.fire("shift", "down")
    fake.fire("shift", "up")
    assert presses == [1] and releases == [1]

    hk.stop()
    assert fake.unhook_calls == 1
