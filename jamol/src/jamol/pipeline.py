from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from jamol.actions import execute_open
from jamol.audio_io import play_wav_bytes
from jamol.config import AppEntry
from jamol.intents import match_intent
from jamol.tts import speak

if TYPE_CHECKING:
    from jamol.api_client import RealTimeVoiceApi

logger = logging.getLogger(__name__)


def handle_transcript(
    text: str,
    apps: list[AppEntry],
    *,
    tts_enabled: bool,
    api_client: RealTimeVoiceApi | None = None,
    speaker_id: str | None = None,
    backend_settings: Any | None = None,
) -> None:
    """
    Spoken feedback uses the same path as the web app when ``api_client`` is set:
    ``POST /tts`` then local playback. Otherwise embedded OmniVoice or SAPI.
    """

    def speak_reply(msg: str) -> None:
        if not tts_enabled or not (msg or "").strip():
            return
        if api_client is not None:
            try:
                wav = api_client.tts_wav(msg, speaker_id=speaker_id)
                play_wav_bytes(wav)
            except Exception as e:
                logger.warning("API TTS failed, trying fallback: %s", e)
                _speak_fallback(msg)
        else:
            _speak_fallback(msg)

    def _speak_fallback(msg: str) -> None:
        if backend_settings is not None:
            try:
                from jamol.backend_rtv import speak_omnivoice

                speak_omnivoice(msg, backend_settings)
            except Exception as e:
                logger.warning("Embedded TTS failed: %s", e)
                speak(msg, enabled=True)
        else:
            speak(msg, enabled=True)

    tid = match_intent(text, apps)
    if not tid:
        msg = "Buyruq topilmadi."
        logger.info("%s (text=%r)", msg, text)
        speak_reply(msg)
        return

    result = execute_open(tid, apps)
    logger.info("Action %s: %s", tid, result.message)
    speak_reply(result.message)
