"""
Synchronous WebSocket STT client for ``/ws/voice`` in ``stt_only`` mode.

This mirrors the browser's WS protocol so Jamol uploads audio exactly the
same way the web app does, instead of the one-shot ``POST /stt``. Jamol
never wants the LLM/TTS side of the server pipeline, so we opt in to
``stt_only=true`` in the ``hello`` message and the server only emits a
``transcript`` before returning to ``idle``.
"""

from __future__ import annotations

import json
import logging
from typing import Iterable
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def http_base_to_ws_url(base_url: str, path: str = "/ws/voice") -> str:
    """Convert ``http(s)://host:port`` to ``ws(s)://host:port<path>``."""
    parsed = urlparse(base_url.rstrip("/"))
    if parsed.scheme in ("ws", "wss"):
        scheme = parsed.scheme
    elif parsed.scheme == "https":
        scheme = "wss"
    else:
        scheme = "ws"
    netloc = parsed.netloc or parsed.path
    return urlunparse((scheme, netloc, path, "", "", ""))


def _chunked(data: bytes, size: int) -> Iterable[bytes]:
    for i in range(0, len(data), size):
        yield data[i : i + size]


def transcribe_pcm_via_ws(
    pcm_s16le: bytes,
    *,
    base_url: str,
    sample_rate: int = 16000,
    api_key: str | None = None,
    speaker_id: str | None = None,
    chunk_size_bytes: int = 32 * 1024,
    timeout: float = 60.0,
) -> str:
    """Upload raw PCM over ``/ws/voice`` in ``stt_only`` mode; return transcript."""
    try:
        from websockets.sync.client import connect
    except ImportError as e:
        raise RuntimeError(
            "The 'websockets' package is required for the WebSocket STT path. "
            "Install it in the same environment: pip install websockets\n"
            "Or reinstall Jamol: pip install -e ./jamol"
        ) from e

    if not pcm_s16le:
        return ""

    ws_url = http_base_to_ws_url(base_url)
    if api_key:
        ws_url = f"{ws_url}?token={api_key}"

    hello: dict = {
        "type": "hello",
        "sampleRate": int(sample_rate),
        "encoding": "pcm_s16le",
        "stt_only": True,
    }
    if speaker_id and str(speaker_id).strip():
        hello["speakerId"] = str(speaker_id).strip()

    logger.debug("WS STT connecting: %s (%d bytes PCM)", ws_url, len(pcm_s16le))

    with connect(
        ws_url,
        open_timeout=timeout,
        close_timeout=5.0,
        max_size=None,
    ) as ws:
        ws.send(json.dumps(hello))
        for chunk in _chunked(pcm_s16le, max(1024, chunk_size_bytes)):
            ws.send(chunk)
        ws.send(json.dumps({"type": "end_utterance"}))

        transcript = ""
        while True:
            try:
                msg = ws.recv(timeout=timeout)
            except TimeoutError as e:
                raise RuntimeError(
                    f"No transcript received within {timeout:.0f}s"
                ) from e

            if isinstance(msg, (bytes, bytearray)):
                continue

            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                logger.debug("WS STT ignoring non-JSON text: %r", msg[:80])
                continue

            mtype = data.get("type")
            if mtype == "error":
                raise RuntimeError(
                    f"WS STT error {data.get('code')!r}: {data.get('message') or ''}"
                )
            if mtype == "transcript" and data.get("final"):
                transcript = (data.get("text") or "").strip()
                break

    return transcript
