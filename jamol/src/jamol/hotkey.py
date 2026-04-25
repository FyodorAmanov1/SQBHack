"""
Global push-to-talk hotkey for Windows (single-key, no modifiers).

Uses the ``keyboard`` package, which hooks the OS-level key stream. This works
while the GUI is not focused (the whole point of a PTT hotkey). Modifier
combinations (``Ctrl+Alt+Space``) intentionally aren't supported here — getting
reliable KEY_UP events for modifier combos across keyboard layouts is fragile,
and a single well-known key (``F9`` by default) is what desktop PTT apps use.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


def _import_keyboard():
    try:
        import keyboard  # type: ignore[import-not-found]
    except ImportError:
        return None
    return keyboard


def is_available() -> bool:
    """True if the ``keyboard`` package can be imported in this env."""
    return _import_keyboard() is not None


class PushToTalkHotkey:
    """Call ``on_press`` when ``key`` goes down, ``on_release`` when it comes up.

    Press events are debounced — the OS auto-repeats held keys, so we only
    fire ``on_press`` on the first transition from up -> down.
    """

    def __init__(
        self,
        key: str,
        *,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self.key = (key or "").strip() or "f9"
        self._on_press = on_press
        self._on_release = on_release
        self._hook_handle = None
        self._pressed = False
        self._lock = threading.Lock()

    def start(self) -> bool:
        kb = _import_keyboard()
        if kb is None:
            logger.warning(
                "'keyboard' package not installed; global hotkey disabled. "
                "Install: pip install keyboard"
            )
            return False
        if self._hook_handle is not None:
            return True

        target = self.key.lower()

        def _handler(event) -> None:  # noqa: ANN001 - keyboard.KeyboardEvent
            name = (getattr(event, "name", None) or "").lower()
            if name != target:
                return
            etype = getattr(event, "event_type", "")
            with self._lock:
                if etype == "down" and not self._pressed:
                    self._pressed = True
                    pressed_now = True
                    released_now = False
                elif etype == "up" and self._pressed:
                    self._pressed = False
                    pressed_now = False
                    released_now = True
                else:
                    return
            if pressed_now:
                try:
                    self._on_press()
                except Exception:
                    logger.exception("PTT on_press callback failed")
            elif released_now:
                try:
                    self._on_release()
                except Exception:
                    logger.exception("PTT on_release callback failed")

        try:
            self._hook_handle = kb.hook(_handler)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to register global hotkey %r: %s", self.key, e)
            return False
        logger.info("Global PTT hotkey armed: %s", self.key.upper())
        return True

    def stop(self) -> None:
        kb = _import_keyboard()
        if kb is None or self._hook_handle is None:
            self._hook_handle = None
            return
        try:
            kb.unhook(self._hook_handle)
        except Exception:
            logger.debug("Error unhooking PTT hotkey", exc_info=True)
        self._hook_handle = None
        with self._lock:
            self._pressed = False
