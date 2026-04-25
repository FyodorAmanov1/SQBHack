from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import AliasChoices, BaseModel, Field

from app.config import Settings, get_settings
from app.services import llm as llm_svc
from app.services import stt as stt_svc
from app.services import tts as tts_svc
from app.services import voices as voices_svc

logger = logging.getLogger(__name__)


def _check_api_key(
    settings: Settings,
    x_api_key: str | None,
    authorization: str | None,
) -> None:
    secret = (settings.api_shared_secret or "").strip()
    if not secret:
        return
    provided = (x_api_key or "").strip()
    if not provided and authorization and authorization.lower().startswith(
        "bearer ",
    ):
        provided = authorization[7:].strip()
    if provided != secret:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def require_optional_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
) -> None:
    _check_api_key(settings, x_api_key, authorization)


router = APIRouter(
    tags=["services"],
    dependencies=[Depends(require_optional_api_key)],
)

@router.get("/client-analytics/{client_id}")
async def get_client_analytics(client_id: str):
    """
    Simulates a database fetch for a specific client's analytics.
    Use this endpoint to populate the operator's financial dashboard.
    """
    return {
        "client_id": client_id,
        "name": "Sarah Johnson",
        "creditScore": 742,
        "accounts": [
            {"id": "1", "type": "Credit Card", "balance": 1250.0, "limit": 5000.0},
            {"id": "2", "type": "Personal Loan", "balance": 4500.0, "limit": 10000.0},
        ],
        "history": [
            {"date": "2024-03-01", "event": "On-time payment - Credit Card"},
            {"date": "2024-02-15", "event": "New account opened - Personal Loan"},
            {"date": "2023-11-10", "event": "Credit line increase approved"},
        ],
        "relatives": [
            {"name": "Mark Johnson", "relation": "Spouse", "linked_accounts": 1}
        ]
    }


class LlmRequest(BaseModel):
    messages: list[dict[str, str]] = Field(
        ...,
        description="OpenAI-style messages with role and content",
    )


class LlmResponse(BaseModel):
    text: str


class VoiceOut(BaseModel):
    model_config = {"populate_by_name": True}
    id: str
    label: str
    filename: str


class VoicesResponse(BaseModel):
    model_config = {"populate_by_name": True}
    voices: list[VoiceOut]
    default_speaker_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("default_speaker_id", "defaultSpeakerId"),
        serialization_alias="defaultSpeakerId",
    )


class TtsRequest(BaseModel):
    model_config = {"populate_by_name": True}
    text: str
    speaker_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("speaker_id", "speakerId"),
    )


class VoiceReplyRequest(BaseModel):
    """Single‑shot HTTP analog of the WS voice pipeline.

    Used by the browser when the WebSocket is unreliable (NAT/proxy kills idle
    TCP). The server runs LLM + TTS and returns the WAV; the reply text is
    exposed as the ``X-Reply-Text`` response header so no second HTTP round‑trip
    is needed for chat display.
    """

    model_config = {"populate_by_name": True}
    text: str
    speaker_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("speaker_id", "speakerId"),
    )
    history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Prior user/assistant turns (OpenAI role/content).",
    )


class SttResponse(BaseModel):
    text: str


@router.get(
    "/voices",
    response_model=VoicesResponse,
    response_model_by_alias=True,
)
async def list_voices(
    settings: Annotated[Settings, Depends(get_settings)],
    refresh: Annotated[bool, Query(description="Rescan disk (e.g. after adding WAV files)")] = False,
) -> VoicesResponse:
    """Voices available for TTS speaker selection.

    When ``TTS_BACKEND=edge``, returns the Microsoft Uzbek neural voices (no clone).
    Otherwise returns reference clips under ``tts_voices_scan_dir`` (e.g. ``myVoice/``)
    usable for OmniVoice cloning.
    """
    if tts_svc.active_backend(settings) == "edge":
        from app.services import tts_edge

        return VoicesResponse(
            voices=[
                VoiceOut(id=v["id"], label=v["label"], filename="")
                for v in tts_edge.UZBEK_VOICES
            ],
            default_speaker_id=settings.tts_edge_voice or tts_edge.DEFAULT_UZ_VOICE,
        )

    if refresh:
        voices_svc.refresh_voice_catalog(settings, log=True)
    rows = voices_svc.voice_catalog()
    default_id = voices_svc.default_speaker_id(settings)
    return VoicesResponse(
        voices=[VoiceOut(id=v.id, label=v.label, filename=v.filename) for v in rows],
        default_speaker_id=default_id,
    )


@router.post("/stt", response_model=SttResponse)
async def stt_endpoint(file: UploadFile = File(...)) -> SttResponse:
    settings = get_settings()
    suffix = Path(file.filename or "audio.wav").suffix.lower()
    if suffix not in (".wav", ".flac", ".ogg", ".webm", ".mp3", ".m4a"):
        suffix = ".wav"
    try:
        data = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            text = await asyncio.to_thread(
                stt_svc.transcribe_file, tmp_path, settings
            )
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception as e:
        logger.exception("STT REST failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return SttResponse(text=text)


@router.post("/llm", response_model=LlmResponse)
async def llm_endpoint(body: LlmRequest) -> LlmResponse:
    settings = get_settings()
    try:
        text = await llm_svc.generate_from_messages(body.messages, settings)
    except Exception as e:
        logger.exception("LLM REST failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return LlmResponse(text=text)


@router.post("/tts")
async def tts_endpoint(body: TtsRequest) -> Response:
    settings = get_settings()
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")
    backend = tts_svc.active_backend(settings)
    raw_speaker = (body.speaker_id or "").strip()
    voice_ref: str | None = None
    if raw_speaker:
        if backend == "edge":
            # Edge voice ids (e.g. ``uz-UZ-SardorNeural``) aren't in the local clip
            # catalog — pass them through; ``tts_edge.resolve_voice`` will normalize.
            voice_ref = raw_speaker
        else:
            hit = voices_svc.get_voice(raw_speaker)
            if hit:
                voice_ref = hit.id
    try:
        if backend == "edge":
            # Edge TTS is already async; don't off-load to a thread (would force a
            # nested event loop for asyncio.run inside the sync helper).
            from app.services import tts_edge

            wav = await tts_edge.synthesize_wav_bytes(
                body.text.strip(),
                voice=voice_ref or settings.tts_edge_voice,
                speed=settings.tts_speed,
            )
        else:
            wav = await asyncio.to_thread(
                tts_svc.text_to_speech_wav_bytes,
                body.text.strip(),
                settings,
                voice_ref_path=voice_ref,
            )
    except Exception as e:
        logger.exception("TTS REST failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return Response(
        content=wav,
        media_type="audio/wav",
        headers={"X-Sample-Rate": "24000"},
    )


@router.post("/voice_reply")
async def voice_reply_endpoint(body: VoiceReplyRequest) -> Response:
    """LLM + TTS in one HTTP call. Browser fallback for flaky WebSocket paths."""
    settings = get_settings()
    user_text = (body.text or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Empty text")

    try:
        history = [
            {"role": str(m.get("role") or ""), "content": str(m.get("content") or "")}
            for m in (body.history or [])
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ]
        reply_text = await llm_svc.generate_reply_with_history(
            user_text, history, settings
        )
    except Exception as e:
        logger.exception("voice_reply LLM failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    reply_text = (reply_text or "").strip()
    if not reply_text:
        raise HTTPException(status_code=502, detail="LLM returned empty reply")

    backend = tts_svc.active_backend(settings)
    raw_speaker = (body.speaker_id or "").strip()
    voice_ref: str | None = None
    if raw_speaker:
        if backend == "edge":
            voice_ref = raw_speaker
        else:
            hit = voices_svc.get_voice(raw_speaker)
            if hit:
                voice_ref = hit.id

    try:
        if backend == "edge":
            from app.services import tts_edge

            wav = await tts_edge.synthesize_wav_bytes(
                reply_text,
                voice=voice_ref or settings.tts_edge_voice,
                speed=settings.tts_speed,
            )
        else:
            wav = await asyncio.to_thread(
                tts_svc.text_to_speech_wav_bytes,
                reply_text,
                settings,
                voice_ref_path=voice_ref,
            )
    except Exception as e:
        logger.exception("voice_reply TTS failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    # Reply text travels in a header so the browser can render it without a
    # second request. Must be URL‑encoded to survive non‑ASCII Uzbek characters.
    from urllib.parse import quote

    return Response(
        content=wav,
        media_type="audio/wav",
        headers={
            "X-Sample-Rate": "24000",
            "X-Reply-Text": quote(reply_text, safe=""),
            "Access-Control-Expose-Headers": "X-Sample-Rate, X-Reply-Text",
        },
    )
