"""
HTTP client for the RealTimeVoice FastAPI app — same routes the frontend uses:
``GET /health``, ``POST /stt``, ``POST /tts``, ``GET /voices``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


def default_api_base() -> str:
    return (os.environ.get("JAMOL_API_BASE") or "http://127.0.0.1:8000").strip().rstrip("/")


def default_api_key() -> str | None:
    k = (os.environ.get("JAMOL_API_KEY") or "").strip()
    return k or None


@dataclass
class RealTimeVoiceApi:
    """Thin wrapper matching ``backend/app/routers/api.py``."""

    base_url: str
    api_key: str | None = None
    timeout: float = 180.0

    @classmethod
    def from_env(cls) -> RealTimeVoiceApi:
        return cls(base_url=default_api_base(), api_key=default_api_key())

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def health(self) -> bool:
        import httpx

        try:
            r = httpx.get(
                f"{self.base_url}/health",
                headers=self._headers(),
                timeout=5.0,
            )
            return r.status_code == 200
        except Exception as e:
            logger.debug("health check failed: %s", e)
            return False

    def stt_upload_wav(self, wav_bytes: bytes, *, filename: str = "speech.wav") -> str:
        """``POST /stt`` — fallback path; prefer :meth:`stt_via_ws` to match the web client."""
        import httpx

        files = {"file": (filename, wav_bytes, "audio/wav")}
        r = httpx.post(
            f"{self.base_url}/stt",
            files=files,
            headers=self._headers(),
            timeout=self.timeout,
        )
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return (data.get("text") or "").strip()

    def stt_via_ws(
        self,
        pcm_s16le: bytes,
        *,
        sample_rate: int = 16000,
        speaker_id: str | None = None,
    ) -> str:
        """Stream PCM to ``/ws/voice`` (``stt_only`` mode) — same protocol as the browser."""
        from jamol.ws_client import transcribe_pcm_via_ws

        return transcribe_pcm_via_ws(
            pcm_s16le,
            base_url=self.base_url,
            sample_rate=sample_rate,
            api_key=self.api_key,
            speaker_id=speaker_id,
            timeout=self.timeout,
        )

    def tts_wav(self, text: str, *, speaker_id: str | None = None) -> bytes:
        """``POST /tts`` — returns WAV bytes (24 kHz, same as browser client)."""
        import httpx

        body: dict[str, Any] = {"text": (text or "").strip()}
        if speaker_id and str(speaker_id).strip():
            body["speakerId"] = str(speaker_id).strip()
        r = httpx.post(
            f"{self.base_url}/tts",
            json=body,
            headers=self._headers(),
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.content

    def list_voices(self) -> list[dict[str, Any]]:
        import httpx

        r = httpx.get(
            f"{self.base_url}/voices",
            headers=self._headers(),
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        return list(data.get("voices") or [])
