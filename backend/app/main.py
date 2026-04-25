from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import api as api_router
from app.services import llm as llm_svc
from app.services import stt as stt_svc
from app.services import tts as tts_svc
from app.services import voices as voices_svc
from app.voice_ws import handle_voice_websocket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    settings = get_settings()
    logger.info("Starting up: loading models…")
    stt_svc.init_model(settings)
    tts_svc.init_model(settings)
    voices_svc.refresh_voice_catalog(settings)
    llm_svc.init_client(settings)
    if settings.llm_provider == "ollama":
        await llm_svc.ping_ollama(settings)
    if settings.tts_warmup_on_start:
        # Done off-thread so model load doesn't block the event loop; first TTS
        # request otherwise pays a 20–30 s cold-start for OmniVoice's internal ASR.
        logger.info("Warming up TTS (forces OmniVoice ASR load)…")
        try:
            await asyncio.to_thread(tts_svc.warmup, settings)
        except Exception:
            logger.exception("TTS warmup failed (non-fatal).")
    yield
    logger.info("Shutdown complete.")


app = FastAPI(title="RealTimeVoice API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/voice")
async def voice_socket(websocket: WebSocket):
    settings = get_settings()
    secret = (settings.api_shared_secret or "").strip()
    if secret:
        token = (websocket.query_params.get("token") or "").strip()
        if token != secret:
            await websocket.close(code=4401)
            return
    await websocket.accept()
    await handle_voice_websocket(websocket)
