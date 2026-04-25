from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from jamol import DEFAULT_SPEAKER_ID
from jamol.api_client import default_api_base, default_api_key
from jamol.audio_mode import resolve_audio
from jamol.config import load_apps_yaml, resolve_config_path
from jamol.pipeline import handle_transcript
from jamol.stt import EngineName
from jamol.voice_loop import run_push_to_talk_loop

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jamol",
        description="Jamol — voice commands via RealTimeVoice STT/TTS + allowlisted actions.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to apps.yaml (default: jamol/config/apps.yaml or apps.example.yaml).",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Run one typed phrase (no microphone).",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Disable spoken confirmations.",
    )
    parser.add_argument(
        "--engine",
        choices=("google", "whisper", "backend"),
        default=os.environ.get("JAMOL_STT_ENGINE", "backend"),
        help="Mic STT when not using API: backend=in-process Whisper; google/whisper=legacy.",
    )
    parser.add_argument(
        "--api-base",
        default=default_api_base(),
        help="RealTimeVoice FastAPI base URL (default: JAMOL_API_BASE or http://127.0.0.1:8000).",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional X-API-Key (or JAMOL_API_KEY) if the server sets api_shared_secret.",
    )
    parser.add_argument(
        "--speaker-id",
        default=os.environ.get("JAMOL_SPEAKER_ID") or DEFAULT_SPEAKER_ID,
        help=(
            "TTS speaker id from GET /voices (API mode only). "
            f"Default: {DEFAULT_SPEAKER_ID} (Microsoft's Uzbek male neural voice for "
            "Edge TTS backend; ignored harmlessly on OmniVoice). "
            "Override with this flag or JAMOL_SPEAKER_ID."
        ),
    )
    parser.add_argument(
        "--embedded-audio",
        action="store_true",
        help="Do not call HTTP API; load STT/TTS in-process (needs jamol[backend]).",
    )
    parser.add_argument(
        "--stt-timeout",
        type=float,
        default=8.0,
        help="(Legacy Google STT) seconds to wait for speech to start.",
    )
    parser.add_argument(
        "--phrase-time-limit",
        type=float,
        default=12.0,
        help="Max seconds of audio per utterance (API + embedded recording).",
    )
    parser.add_argument("--whisper-model", default="base", help="(Legacy) local Whisper size.")
    parser.add_argument("--whisper-device", default="cpu", help="(Legacy) Whisper device.")
    parser.add_argument(
        "--whisper-compute-type",
        default="int8",
        help="(Legacy) Whisper compute type.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Open graphical window.",
    )
    parser.add_argument(
        "--mic-device",
        type=int,
        default=None,
        help="Input device index from sounddevice.query_devices() (default: system default).",
    )
    parser.add_argument(
        "--no-vad",
        action="store_true",
        help="Disable WebRTC VAD silence auto-stop (fall back to fixed-duration capture).",
    )
    parser.add_argument(
        "--hotkey",
        default="f9",
        help="Global push-to-talk key name in the GUI (default: f9). Single-key only.",
    )
    args = parser.parse_args(argv)

    _configure_logging(args.log_level)

    if sys.platform != "win32":
        logger.warning("Jamol targets Windows for command execution; audio may still work.")

    cfg_path = resolve_config_path(args.config)
    apps = load_apps_yaml(cfg_path)
    tts_enabled = not args.no_tts

    api_client, embedded_settings = resolve_audio(args)
    if args.engine == "backend" and api_client is None and embedded_settings is None:
        return 1

    speaker_id = (args.speaker_id or "").strip() or None

    if args.text is not None:
        handle_transcript(
            args.text,
            apps,
            tts_enabled=tts_enabled,
            api_client=api_client,
            speaker_id=speaker_id,
            backend_settings=embedded_settings,
        )
        return 0

    if args.gui:
        from jamol.gui import run_gui

        return run_gui(args)

    engine: EngineName = args.engine
    print("Jamol — phrases:", cfg_path)
    if api_client:
        print("Audio: RealTimeVoice API at", api_client.base_url)
    elif embedded_settings is not None:
        print("Audio: embedded STT/TTS (in-process)")

    def on_text(t: str) -> None:
        handle_transcript(
            t,
            apps,
            tts_enabled=tts_enabled,
            api_client=api_client,
            speaker_id=speaker_id,
            backend_settings=embedded_settings,
        )

    run_push_to_talk_loop(
        on_text,
        engine=engine,
        stt_timeout=args.stt_timeout,
        phrase_time_limit=args.phrase_time_limit,
        whisper_model=args.whisper_model,
        whisper_device=args.whisper_device,
        whisper_compute_type=args.whisper_compute_type,
        backend_settings=embedded_settings,
        api_client=api_client,
        device_index=args.mic_device,
        vad_enabled=not args.no_vad,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
