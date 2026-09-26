"""The dashboard must only answer the dashboard itself: other websites open in the
browser must not reach /ws (chat -> LLM -> run_python) or the REST API."""
import copy
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


# --- API keys: only environment variable names are stored (config.yaml is in a public repo) ---

@pytest.fixture
def cfg(monkeypatch):
    data = {"llm": {"active_provider": "deepseek", "providers": {
        "deepseek": {"type": "openai", "label": "DeepSeek", "model": "m",
                     "base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
        "old": {"type": "openai", "label": "Old", "model": "m", "base_url": "http://x",
                "api_key": "sk-legacy-secret"}}}}
    main = types.ModuleType("sebastian.main")
    main._load_config = lambda: copy.deepcopy(data)
    main._save_config = lambda c: (data.clear(), data.update(copy.deepcopy(c)))
    main.get_providers = lambda: data["llm"]["providers"]
    main.get_active_provider = lambda: data["llm"]["active_provider"]
    monkeypatch.setitem(sys.modules, "sebastian.main", main)
    return data


def test_providers_api_never_returns_keys(client, cfg):
    r = client.get("/api/providers")
    assert r.status_code == 200 and "sk-legacy-secret" not in r.text
    assert r.json()["providers"]["deepseek"]["api_key_env"] == "DEEPSEEK_API_KEY"


def test_new_provider_stores_variable_name_only(client, cfg):
    r = client.put("/api/providers/openrouter", json={
        "type": "openai", "label": "OpenRouter", "model": "x", "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY"})
    assert r.status_code == 200
    assert cfg["llm"]["providers"]["openrouter"]["api_key_env"] == "OPENROUTER_API_KEY"
    assert "api_key" not in cfg["llm"]["providers"]["openrouter"]


@pytest.mark.parametrize("body", [{"api_key": "sk-or-v1-abc123"},          # the key itself
                                  {"api_key_env": "sk-or-v1-abc123"},      # pasted into the name field
                                  {"api_key_env": "a1b2c3d4e5f6a7b8c9d0"}])  # lowercase hex key
def test_raw_keys_are_refused(client, cfg, body):
    before = copy.deepcopy(cfg)
    r = client.put("/api/providers/openrouter", json={"type": "openai", "model": "x", "base_url": "u", **body})
    assert r.status_code == 400 and "setx" in r.json()["message"]
    assert cfg == before


def test_editing_old_provider_keeps_its_existing_key(client, cfg):
    client.put("/api/providers/old", json={"type": "openai", "label": "Old", "model": "m2", "base_url": "http://x"})
    assert cfg["llm"]["providers"]["old"] == {"type": "openai", "label": "Old", "model": "m2",
                                              "base_url": "http://x", "api_key": "sk-legacy-secret"}
