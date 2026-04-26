"""POST /operator-advice returns three panels when the LLM stub succeeds."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("STT_ENABLED", "false")
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

    return TestClient(main_mod.app)


async def _fake_panels(client_context: str, transcript: str, settings) -> list[dict[str, str]]:
    return [
        {"title": "Darhol", "content": "A1"},
        {"title": "Muloqot", "content": "A2"},
        {"title": "Xavf", "content": "A3"},
    ]


def test_operator_advice_schema(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm as llm_svc

    monkeypatch.setattr(llm_svc, "generate_operator_advice_panels", _fake_panels)

    r = api_client.post(
        "/operator-advice",
        json={
            "client_id": "AD0135673",
            "transcript": "Assalomu alaykum, kreditim bo‘yicha so‘rayapman",
            "use_server_client_context": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "panels" in data
    assert len(data["panels"]) == 3
    assert data["panels"][0]["title"] == "Darhol"
    assert "updatedAt" in data


def test_stt_endpoint_501_when_disabled(
    api_client: TestClient,
) -> None:
    files = {"file": ("a.wav", b"RIFF", "audio/wav")}
    r = api_client.post("/stt", files=files)
    assert r.status_code == 501
    body = r.json()
    assert "detail" in body


def test_voice_ws_closes_with_stt_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STT_ENABLED", "false")
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

    client = TestClient(main_mod.app)
    with client.websocket_connect("/ws/voice") as ws:
        msg = json.loads(ws.receive_text())
    assert msg["type"] == "error"
    assert msg["code"] == "STT_DISABLED"
