from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        import pyttsx3

        _engine = pyttsx3.init()
    return _engine


def speak(text: str, *, enabled: bool = True) -> None:
    if not enabled or not text.strip():
        return
    try:
        eng = _get_engine()
        eng.say(text)
        eng.runAndWait()
    except OSError as e:
        logger.warning("TTS unavailable: %s", e)
