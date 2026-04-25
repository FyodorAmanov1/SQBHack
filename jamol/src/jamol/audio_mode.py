"""Resolve API vs embedded STT/TTS (shared by CLI and GUI)."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from jamol.api_client import RealTimeVoiceApi, default_api_base, default_api_key

logger = logging.getLogger(__name__)


def resolve_audio(
    args: argparse.Namespace,
) -> tuple[RealTimeVoiceApi | None, Any | None]:
    """
    Prefer HTTP ``/stt`` and ``/tts``; else embedded ``app.services`` when possible.
    """
    if getattr(args, "embedded_audio", False):
        from jamol.backend_rtv import load_backend_settings

        try:
            return None, load_backend_settings()
        except Exception as e:
            logger.error("Embedded audio unavailable: %s", e)
            return None, None

    api = RealTimeVoiceApi(
        str(getattr(args, "api_base", default_api_base())),
        (getattr(args, "api_key", None) or default_api_key()),
    )
    if api.health():
        logger.info("Using RealTimeVoice API at %s", api.base_url)
        return api, None

    if args.engine == "backend":
        from jamol.backend_rtv import try_load_backend_settings

        emb = try_load_backend_settings()
        if emb is not None:
            logger.warning(
                "API not reachable at %s — falling back to embedded models.",
                api.base_url,
            )
            return None, emb

    if args.engine in ("google", "whisper"):
        logger.warning(
            "API not reachable — using %s STT (not the server stack).",
            args.engine,
        )
        return None, None

    logger.error(
        "RealTimeVoice API not running at %s. Start: cd backend && uvicorn app.main:app",
        api.base_url,
    )
    return None, None
