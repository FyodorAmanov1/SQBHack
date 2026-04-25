from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from jamol.stt import EngineName, listen_and_transcribe

logger = logging.getLogger(__name__)


def run_push_to_talk_loop(
    on_transcript: Callable[[str], None],
    *,
    engine: EngineName,
    stt_timeout: float,
    phrase_time_limit: float | None,
    whisper_model: str,
    whisper_device: str,
    whisper_compute_type: str,
    backend_settings: Any | None = None,
    api_client: Any | None = None,
    device_index: int | None = None,
    vad_enabled: bool = True,
) -> None:
    """
    Press Enter to arm listening; speak; VAD (or a timeout) ends the capture and
    the transcript is passed to the callback. Type 'q' + Enter to exit.
    """
    print("Jamol: push-to-talk. Enter — listen, q + Enter — quit.")
    while True:
        try:
            line = input(">>> [Enter=speak, q=quit] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line == "q":
            break

        try:
            text = listen_and_transcribe(
                engine=engine,
                timeout=stt_timeout,
                phrase_time_limit=phrase_time_limit,
                whisper_model=whisper_model,
                whisper_device=whisper_device,
                whisper_compute_type=whisper_compute_type,
                backend_settings=backend_settings,
                api_client=api_client,
                device_index=device_index,
                vad_enabled=vad_enabled,
            )
        except RuntimeError as e:
            logger.warning("%s", e)
            print(e)
            continue
        if not text:
            logger.info("No transcript.")
            print("(no speech recognized)")
            continue

        logger.info("Transcript: %s", text)
        print(f"Heard: {text}")
        on_transcript(text)
