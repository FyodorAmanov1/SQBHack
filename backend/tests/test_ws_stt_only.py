"""WebSocket ``/ws/voice`` ``stt_only`` mode: STT only, no LLM/TTS invocation."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Stub out model loads and services so the FastAPI app can start offline."""
    monkeypatch.setenv("STT_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    from app import main as main_mod
    from app.services import llm as llm_svc
    from app.services import stt as stt_svc
    from app.services import tts as tts_svc
    from app.services import voices as voices_svc

    monkeypatch.setattr(stt_svc, "init_model", lambda *a, **kw: None)
    monkeypatch.setattr(tts_svc, "init_model", lambda *a, **kw: None)
    monkeypatch.setattr(voices_svc, "refresh_voice_catalog", lambda *a, **kw: 0)
    monkeypatch.setattr(llm_svc, "init_client", lambda *a, **kw: None)

    async def _noop_ping(_settings):
        return None

    monkeypatch.setattr(llm_svc, "ping_ollama", _noop_ping)

    # Any audio -> fixed transcript (the real model is not loaded).
    monkeypatch.setattr(
        stt_svc, "transcribe_pcm", lambda pcm, sr, settings: "salom dunyo"
    )

    called: dict[str, bool] = {"llm": False, "tts": False}

    async def _fail_llm(*a, **kw):
        called["llm"] = True
        raise AssertionError("LLM must not be called in stt_only mode")

    def _fail_tts(*a, **kw):
        called["tts"] = True
        raise AssertionError("TTS must not be called in stt_only mode")

    monkeypatch.setattr(llm_svc, "generate_reply_with_history", _fail_llm)
    monkeypatch.setattr(tts_svc, "synthesize_to_tensor", _fail_tts)

    return TestClient(main_mod.app)


def _recv_json(ws) -> dict:
    raw = ws.receive_text()
    return json.loads(raw)


def test_stt_only_transcript_no_llm_no_tts(client: TestClient) -> None:
    """hello(stt_only) + dummy PCM + end_utterance -> transcript, no LLM/TTS calls."""
    with client.websocket_connect("/ws/voice") as ws:
        greeting = _recv_json(ws)
        assert greeting["type"] == "status"
        assert greeting["stage"] == "idle"

        ws.send_text(
            json.dumps(
                {
                    "type": "hello",
                    "sampleRate": 16000,
                    "encoding": "pcm_s16le",
                    "stt_only": True,
                }
            )
        )
        ack = _recv_json(ws)
        assert ack["type"] == "status"
        assert ack["stage"] == "idle"

        ws.send_bytes(b"\x00\x00" * 1600)
        ws.send_text(json.dumps({"type": "end_utterance"}))

        stage = _recv_json(ws)
        assert stage["type"] == "status"
        assert stage["stage"] == "stt"

        transcript = _recv_json(ws)
        assert transcript["type"] == "transcript"
        assert transcript["final"] is True
        assert transcript["text"] == "salom dunyo"

        done = _recv_json(ws)
        assert done["type"] == "status"
        assert done["stage"] == "idle"


def test_stt_only_rejects_text_utterance(client: TestClient) -> None:
    """``text_utterance`` is disabled under ``stt_only`` (there is no LLM/TTS path)."""
    with client.websocket_connect("/ws/voice") as ws:
        _recv_json(ws)
        ws.send_text(
            json.dumps(
                {
                    "type": "hello",
                    "sampleRate": 16000,
                    "encoding": "pcm_s16le",
                    "stt_only": True,
                }
            )
        )
        _recv_json(ws)

        ws.send_text(
            json.dumps({"type": "text_utterance", "text": "salom"})
        )
        err = _recv_json(ws)
        assert err["type"] == "error"
        assert err["code"] == "STT_ONLY"
