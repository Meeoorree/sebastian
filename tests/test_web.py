"""The dashboard must only answer the dashboard itself: other websites open in the
browser must not reach /ws (chat -> LLM -> run_python) or the REST API."""
import importlib
import sys
import types

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

GOOD = "http://localhost:7860"
EVIL = "http://evil.example"
WS = "ws://127.0.0.1:7860/ws"  # full URL: websocket_connect ignores base_url


@pytest.fixture
def client(monkeypatch):
    # sebastian.tts imports sounddevice (needs PortAudio); the web tests don't speak.
    tts = types.ModuleType("sebastian.tts")
    tts.speak_streamed = tts.stop_speaking = tts.is_speaking = lambda *a: None
    monkeypatch.setitem(sys.modules, "sebastian.tts", tts)
    monkeypatch.delitem(sys.modules, "sebastian.web", raising=False)
    web = importlib.import_module("sebastian.web")
    yield TestClient(web.app, base_url="http://127.0.0.1:7860")
    sys.modules.pop("sebastian.web", None)


def test_ws_refuses_foreign_origin(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS, headers={"origin": EVIL}) as ws:
            ws.receive_text()
    assert exc.value.code == 1008  # refused by the origin check, not something else


def test_ws_accepts_own_origin(client):
    for origin in (GOOD, "http://127.0.0.1:7860"):
        with client.websocket_connect(WS, headers={"origin": origin}) as ws:
            assert "connected" in ws.receive_text()


def test_api_refuses_foreign_origin(client):
    assert client.post("/api/mute", headers={"origin": EVIL}).status_code == 403


def test_page_served_to_own_origin(client):
    assert client.get("/", headers={"origin": GOOD}).status_code == 200


def test_refuses_foreign_host_header(client):
    # DNS rebinding: evil.example resolves to 127.0.0.1, so the Host header is foreign.
    assert client.get("/", headers={"host": "evil.example:7860"}).status_code == 400
