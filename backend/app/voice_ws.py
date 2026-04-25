from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from app.config import get_settings
from app.services import llm as llm_svc
from app.services import stt as stt_svc
from app.services import tts as tts_svc
from app.services import voices as voices_svc

logger = logging.getLogger(__name__)


def _pcm_chunk_samples(settings) -> int:
    ms = max(8, settings.tts_pcm_chunk_ms)
    return max(1, int(24000 * ms / 1000))


def _resolve_ws_speaker(settings, raw: str) -> str | None:
    """Normalize a WebSocket ``speakerId`` for the active TTS backend.

    - ``omnivoice``: must match a clip in :mod:`app.services.voices`.
    - ``edge``: accept any Microsoft Uzbek voice id that
      :func:`tts_edge.resolve_voice` understands (e.g. ``uz-UZ-MadinaNeural``).

    Returns the canonical id to forward to the TTS layer, or ``None`` when the
    id can't be mapped so the caller logs and falls back to the env default.
    """
    key = (raw or "").strip()
    if not key:
        return None
    ent = voices_svc.get_voice(key)
    if ent:
        return ent.id
    if tts_svc.active_backend(settings) == "edge":
        from app.services import tts_edge

        resolved = tts_edge.resolve_voice(key)
        known = {v["id"] for v in tts_edge.UZBEK_VOICES}
        if resolved in known:
            return resolved
    return None


async def handle_voice_websocket(websocket: WebSocket) -> None:
    """WebSocket must already be accepted (e.g. after optional auth in main)."""
    correlation_id = uuid.uuid4().hex[:12]
    settings = get_settings()
    buffer = bytearray()
    client_sr = 16000
    encoding = "pcm_s16le"
    hello_ok = False
    # When true, `end_utterance` emits the transcript only (no LLM or TTS).
    # Opt-in per session via `hello.stt_only = true`; browser client leaves this false.
    stt_only_mode = False
    llm_history: list[dict[str, str]] = []
    pipeline_lock = asyncio.Lock()
    # Catalog speaker: repo-relative path (same as GET /voices `id`), or None for .env default only.
    ws_voice_ref: str | None = None

    async def send_json(obj: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(obj, ensure_ascii=False))

    async def voice_reply_from_text(user_text: str) -> None:
        """LLM + TTS after transcript is known (server STT or client Web Speech API)."""
        await send_json(
            {
                "type": "transcript",
                "text": user_text,
                "final": True,
            }
        )
        if not user_text.strip():
            await send_json(
                {
                    "type": "status",
                    "stage": "idle",
                    "detail": "Matn topilmadi, qayta urinib ko‘ring.",
                }
            )
            return

        await send_json(
            {
                "type": "status",
                "stage": "llm",
                "detail": "Javob tayyorlanmoqda…",
            }
        )
        t_llm = time.monotonic()
        reply = await llm_svc.generate_reply_with_history(
            user_text.strip(),
            llm_history,
            settings,
        )
        llm_ms = (time.monotonic() - t_llm) * 1000.0
        logger.info(
            "[%s] voice pipeline llm_ms=%.0f",
            correlation_id,
            llm_ms,
        )

        await send_json({"type": "reply_text", "text": reply})

        await send_json(
            {
                "type": "status",
                "stage": "tts",
                "detail": "Ovozga aylantirilmoqda…",
            }
        )
        t_tts = time.monotonic()
        backend = tts_svc.active_backend(settings)
        voice_ref: str | None = None
        if ws_voice_ref:
            if backend == "edge":
                # Edge voice ids aren't in the local clip catalog — trust the value
                # and let tts_edge.resolve_voice normalize it.
                voice_ref = ws_voice_ref
            else:
                hit = voices_svc.get_voice(ws_voice_ref)
                if hit:
                    voice_ref = hit.id
        chunk_samples = _pcm_chunk_samples(settings)

        await send_json(
            {
                "type": "audio_meta",
                "sampleRate": 24000,
                "encoding": "pcm_s16le",
            }
        )

        # Streaming path is a simple sentence splitter + backend-agnostic
        # synth-per-segment. Edge TTS returns each segment in ~1 s so the
        # user hears the first sentence within ~1-2 s even for long replies;
        # OmniVoice is slower per segment but still benefits from overlap.
        if settings.tts_stream_segments:
            segments = tts_svc.split_text_for_tts(
                reply,
                min_chars=settings.tts_stream_min_chars,
                max_chars=settings.tts_stream_max_chars,
            ) or [reply]
            first_audio_ms: float | None = None
            for idx, seg in enumerate(segments, start=1):
                t_seg = time.monotonic()
                pcm, sr = await tts_svc.asynthesize_pcm_bytes(
                    seg, settings, voice_ref_path=voice_ref
                )
                if first_audio_ms is None:
                    first_audio_ms = (time.monotonic() - t_tts) * 1000.0
                    logger.info(
                        "[%s] voice pipeline tts_first_audio_ms=%.0f backend=%s "
                        "segment 1/%d",
                        correlation_id,
                        first_audio_ms,
                        backend,
                        len(segments),
                    )
                logger.debug(
                    "[%s] tts seg %d/%d len=%d chars seg_ms=%.0f",
                    correlation_id,
                    idx,
                    len(segments),
                    len(seg),
                    (time.monotonic() - t_seg) * 1000.0,
                )
                for part in tts_svc.pcm_bytes_to_chunks(pcm, chunk_samples):
                    await websocket.send_bytes(part)
        else:
            pcm, sr = await tts_svc.asynthesize_pcm_bytes(
                reply, settings, voice_ref_path=voice_ref
            )
            for part in tts_svc.pcm_bytes_to_chunks(pcm, chunk_samples):
                await websocket.send_bytes(part)

        tts_ms = (time.monotonic() - t_tts) * 1000.0
        logger.info(
            "[%s] voice pipeline tts_total_ms=%.0f",
            correlation_id,
            tts_ms,
        )
        await send_json(
            {
                "type": "status",
                "stage": "idle",
                "detail": "Tayyor.",
            }
        )

        ut = user_text.strip()
        rt = reply.strip()
        if ut and rt:
            llm_history.append({"role": "user", "content": ut})
            llm_history.append({"role": "assistant", "content": rt})
            llm_svc.trim_llm_history(llm_history, settings.llm_history_max_messages)

    try:
        await send_json({"type": "status", "stage": "idle", "detail": "Ulanish tayyor."})
    except Exception:
        return

    while True:
        try:
            message = await websocket.receive()
        except WebSocketDisconnect:
            break
        except RuntimeError as e:
            if "disconnect" in str(e).lower():
                break
            raise

        if message.get("type") == "websocket.disconnect":
            break

        if "bytes" in message and message["bytes"] is not None:
            raw = message["bytes"]
            chunk = raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)
            if not hello_ok:
                await send_json(
                    {
                        "type": "error",
                        "code": "PROTOCOL",
                        "message": "Avval hello yuboring.",
                    }
                )
                continue
            if len(buffer) + len(chunk) > settings.max_audio_bytes:
                await send_json(
                    {
                        "type": "error",
                        "code": "AUDIO_TOO_LARGE",
                        "message": "Audio juda uzun.",
                    }
                )
                buffer.clear()
                continue
            buffer.extend(chunk)
            continue

        if "text" in message and message["text"] is not None:
            try:
                data = json.loads(message["text"])
            except json.JSONDecodeError:
                await send_json(
                    {
                        "type": "error",
                        "code": "BAD_JSON",
                        "message": "Noto‘g‘ri JSON.",
                    }
                )
                continue

            msg_type = data.get("type")
            if msg_type == "ping":
                # Heartbeat for flaky NAT/proxy paths; allowed before hello so
                # the client can probe the socket immediately after open.
                await send_json({"type": "pong"})
                continue

            if msg_type == "hello":
                client_sr = int(data.get("sampleRate") or 16000)
                encoding = str(data.get("encoding") or "pcm_s16le")
                sp = data.get("speakerId") if "speakerId" in data else data.get("speaker_id")
                ws_voice_ref = None
                if sp is not None and str(sp).strip():
                    resolved = _resolve_ws_speaker(settings, str(sp))
                    if resolved:
                        ws_voice_ref = resolved
                    else:
                        logger.warning(
                            "[%s] Unknown speakerId %r; using default ref from env.",
                            correlation_id,
                            sp,
                        )
                stt_only_mode = bool(
                    data.get("stt_only") if "stt_only" in data else data.get("sttOnly")
                )
                hello_ok = True
                buffer.clear()
                llm_history.clear()
                await send_json(
                    {
                        "type": "status",
                        "stage": "idle",
                        "detail": "Salom! Gapirishni boshlashingiz mumkin.",
                    }
                )
                continue

            if msg_type == "set_speaker":
                if not hello_ok:
                    await send_json(
                        {
                            "type": "error",
                            "code": "PROTOCOL",
                            "message": "Avval hello yuboring.",
                        }
                    )
                    continue
                sp = data.get("speakerId") if "speakerId" in data else data.get("speaker_id")
                ws_voice_ref = None
                if sp is not None and str(sp).strip():
                    resolved = _resolve_ws_speaker(settings, str(sp))
                    if resolved:
                        ws_voice_ref = resolved
                    else:
                        logger.warning(
                            "[%s] set_speaker: unknown id %r",
                            correlation_id,
                            sp,
                        )
                await send_json(
                    {
                        "type": "status",
                        "stage": "idle",
                        "detail": "Ovoz tanlandi.",
                    }
                )
                continue

            if msg_type == "reset_history":
                llm_history.clear()
                await send_json(
                    {
                        "type": "status",
                        "stage": "idle",
                        "detail": "Suhbat xotirasi tozalandi.",
                    }
                )
                continue

            if msg_type == "cancel":
                buffer.clear()
                await send_json(
                    {"type": "status", "stage": "idle", "detail": "Bekor qilindi."}
                )
                continue

            if msg_type == "text_utterance":
                if not hello_ok:
                    await send_json(
                        {
                            "type": "error",
                            "code": "PROTOCOL",
                            "message": "hello kerak.",
                        }
                    )
                    continue
                if stt_only_mode:
                    await send_json(
                        {
                            "type": "error",
                            "code": "STT_ONLY",
                            "message": "text_utterance stt_only rejimida mavjud emas.",
                        }
                    )
                    continue
                raw = data.get("text")
                user_text = str(raw or "").strip()
                if not user_text:
                    await send_json(
                        {
                            "type": "error",
                            "code": "EMPTY_TEXT",
                            "message": "Matn bo‘sh.",
                        }
                    )
                    continue
                if pipeline_lock.locked():
                    await send_json(
                        {
                            "type": "error",
                            "code": "PIPELINE_BUSY",
                            "message": "Avvalgi so‘rov hali ishlanmoqda, biroz kuting.",
                        }
                    )
                    continue

                async with pipeline_lock:
                    try:
                        await voice_reply_from_text(user_text)
                    except RuntimeError as e:
                        logger.warning(
                            "[%s] Voice pipeline: %s", correlation_id, e
                        )
                        await send_json(
                            {
                                "type": "error",
                                "code": "PIPELINE_FAILED",
                                "message": str(e),
                            }
                        )
                        await send_json(
                            {
                                "type": "status",
                                "stage": "idle",
                                "detail": "Xatolik yuz berdi.",
                            }
                        )
                    except Exception:
                        logger.exception(
                            "[%s] Voice pipeline failed", correlation_id
                        )
                        await send_json(
                            {
                                "type": "error",
                                "code": "PIPELINE_FAILED",
                                "message": "Ichki xatolik.",
                            }
                        )
                        await send_json(
                            {
                                "type": "status",
                                "stage": "idle",
                                "detail": "Xatolik yuz berdi.",
                            }
                        )
                continue

            if msg_type == "end_utterance":
                if not hello_ok:
                    await send_json(
                        {
                            "type": "error",
                            "code": "PROTOCOL",
                            "message": "hello kerak.",
                        }
                    )
                    continue
                if encoding != "pcm_s16le":
                    await send_json(
                        {
                            "type": "error",
                            "code": "UNSUPPORTED_ENCODING",
                            "message": "Faqat pcm_s16le qo‘llab-quvvatlanadi.",
                        }
                    )
                    continue
                pcm = bytes(buffer)
                buffer.clear()
                if not pcm:
                    await send_json(
                        {
                            "type": "error",
                            "code": "EMPTY_AUDIO",
                            "message": "Audio bo‘sh.",
                        }
                    )
                    continue

                max_samples = int(settings.max_audio_seconds * client_sr)
                if len(pcm) > max_samples * 2:
                    await send_json(
                        {
                            "type": "error",
                            "code": "AUDIO_TOO_LARGE",
                            "message": "Yozuv juda uzoq.",
                        }
                    )
                    continue

                if pipeline_lock.locked():
                    await send_json(
                        {
                            "type": "error",
                            "code": "PIPELINE_BUSY",
                            "message": "Avvalgi so‘rov hali ishlanmoqda, biroz kuting.",
                        }
                    )
                    continue

                async with pipeline_lock:
                    try:
                        await send_json(
                            {
                                "type": "status",
                                "stage": "stt",
                                "detail": "Nutq matnga aylantirilmoqda…",
                            }
                        )
                        t_stt = time.monotonic()
                        user_text = await asyncio.to_thread(
                            stt_svc.transcribe_pcm, pcm, client_sr, settings
                        )
                        stt_ms = (time.monotonic() - t_stt) * 1000.0
                        logger.info(
                            "[%s] voice pipeline stt_ms=%.0f",
                            correlation_id,
                            stt_ms,
                        )

                        if stt_only_mode:
                            await send_json(
                                {
                                    "type": "transcript",
                                    "text": user_text,
                                    "final": True,
                                }
                            )
                            await send_json(
                                {
                                    "type": "status",
                                    "stage": "idle",
                                    "detail": "Transkript tayyor.",
                                }
                            )
                        else:
                            await voice_reply_from_text(user_text)
                    except RuntimeError as e:
                        logger.warning(
                            "[%s] Voice pipeline: %s", correlation_id, e
                        )
                        await send_json(
                            {
                                "type": "error",
                                "code": "PIPELINE_FAILED",
                                "message": str(e),
                            }
                        )
                        await send_json(
                            {
                                "type": "status",
                                "stage": "idle",
                                "detail": "Xatolik yuz berdi.",
                            }
                        )
                    except Exception:
                        logger.exception(
                            "[%s] Voice pipeline failed", correlation_id
                        )
                        await send_json(
                            {
                                "type": "error",
                                "code": "PIPELINE_FAILED",
                                "message": "Ichki xatolik.",
                            }
                        )
                        await send_json(
                            {
                                "type": "status",
                                "stage": "idle",
                                "detail": "Xatolik yuz berdi.",
                            }
                        )
                continue

            await send_json(
                {
                    "type": "error",
                    "code": "UNKNOWN_TYPE",
                    "message": f"Noma’lum type: {msg_type}",
                }
            )
