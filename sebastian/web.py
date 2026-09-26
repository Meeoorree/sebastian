"""Sebastian Web UI — runs alongside voice as a background thread."""
from __future__ import annotations
import asyncio
import json
import re
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.websockets import WebSocketClose

from sebastian.tts import speak_streamed, stop_speaking, is_speaking

_STATIC_DIR = Path(__file__).parent / "static"
_LOCAL_HOSTS = ["localhost", "127.0.0.1"]
_port = 7860  # set by start_web_background


class _OriginGuard:
    """Refuse requests sent by other websites open in the browser.

    Browsers attach an Origin header to WebSocket and cross-site requests. Without
    this check any page could open ws://127.0.0.1:7860/ws and chat with the LLM,
    which can run code. No Origin (curl, local scripts) is allowed.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            origin = dict(scope["headers"]).get(b"origin")
            allowed = {f"http://{h}:{_port}" for h in _LOCAL_HOSTS}
            if origin is not None and origin.decode("latin-1") not in allowed:
                if scope["type"] == "websocket":
                    await WebSocketClose(code=1008)(scope, receive, send)
                else:
                    await PlainTextResponse("Forbidden origin", status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


app = FastAPI(title="Sebastian")
app.add_middleware(_OriginGuard)
# DNS rebinding: a page on evil.example re-pointed to 127.0.0.1 still sends Host: evil.example.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_LOCAL_HOSTS)
_clients: list[WebSocket] = []
_loop: asyncio.AbstractEventLoop | None = None


# ─── Capture the REAL event loop at startup ───

@app.on_event("startup")
async def _capture_loop():
    global _loop
    _loop = asyncio.get_running_loop()
    print("[Web] Event loop captured — WebSocket broadcast ready.")


# ─── Thread-safe broadcast ───

def _broadcast_to_ws(event: dict) -> None:
    """Send event to all connected WebSocket clients.
    Thread-safe — can be called from voice/keyboard threads."""
    if not _loop or _loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(_async_broadcast(event), _loop)
    except RuntimeError:
        pass  # loop closed during shutdown


async def _async_broadcast(event: dict) -> None:
    """Actually send the event — runs on the event loop thread."""
    data = json.dumps(event)
    for ws in list(_clients):
        try:
            await ws.send_text(data)
        except Exception:
            if ws in _clients:
                _clients.remove(ws)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((_STATIC_DIR / "index.html").read_text(encoding="utf-8"))


# ─── Provider APIs ───

@app.get("/api/providers")
async def api_providers():
    from sebastian.main import get_providers, get_active_provider
    providers = get_providers()
    active = get_active_provider()
    result = {}
    for key, prov in providers.items():
        result[key] = {
            "label": prov.get("label", key),
            "model": prov.get("model", ""),
            "type": prov.get("type", "ollama"),
            "base_url": prov.get("base_url", ""),
            "api_key_env": prov.get("api_key_env", ""),  # a variable name, never the key
        }
    return JSONResponse({"providers": result, "active": active})


@app.post("/api/providers/{provider_key}")
async def api_set_provider(provider_key: str):
    from sebastian.main import set_active_provider
    ok = set_active_provider(provider_key)
    if ok:
        return JSONResponse({"status": "ok", "active": provider_key})
    return JSONResponse({"status": "error", "message": "Unknown provider"}, status_code=400)


_ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]{0,63}")
_KEY_HELP = ('API keys are not saved in config.yaml (it is in a public repo). In a terminal run  '
             'setx OPENROUTER_API_KEY "your-key"  (any name in capitals), restart Sebastian, '
             'and enter the name, e.g. OPENROUTER_API_KEY, as the key variable.')


@app.put("/api/providers/{provider_key}")
async def api_upsert_provider(provider_key: str, request: Request):
    """Add or update a provider. It stores the NAME of the environment variable
    that holds the API key (api_key_env); a raw key is refused."""
    from sebastian.main import _load_config, _save_config
    body = await request.json()
    env = str(body.get("api_key_env") or "").strip()
    if body.get("api_key") or (env and not _ENV_NAME.fullmatch(env)):
        return JSONResponse({"status": "error", "message": _KEY_HELP}, status_code=400)
    cfg = _load_config()
    providers = cfg.setdefault("llm", {}).setdefault("providers", {})
    old = providers.get(provider_key, {})
    new = {
        "type": body.get("type", "openai"),
        "label": body.get("label", provider_key),
        "model": body.get("model", ""),
        "base_url": body.get("base_url", ""),
    }
    if env:
        new["api_key_env"] = env
    if "api_key" in old:
        new["api_key"] = old["api_key"]  # set by hand in an old config; keep it working
    providers[provider_key] = new
    _save_config(cfg)
    return JSONResponse({"status": "ok", "provider": provider_key})


@app.delete("/api/providers/{provider_key}")
async def api_delete_provider(provider_key: str):
    """Delete a provider."""
    from sebastian.main import _load_config, _save_config, get_active_provider
    cfg = _load_config()
    providers = cfg.get("llm", {}).get("providers", {})
    if provider_key not in providers:
        return JSONResponse({"status": "error", "message": "Not found"}, status_code=404)
    if provider_key == get_active_provider():
        return JSONResponse({"status": "error", "message": "Cannot delete active provider"}, status_code=400)
    del providers[provider_key]
    _save_config(cfg)
    return JSONResponse({"status": "ok"})


# ─── Settings APIs ───

@app.get("/api/settings")
async def api_get_settings():
    """Return all configurable settings."""
    from sebastian.main import _load_config
    cfg = _load_config()
    return JSONResponse({
        "tts": cfg.get("tts", {}),
        "stt": cfg.get("stt", {}),
        "wake_word": cfg.get("wake_word", {}),
        "context": cfg.get("context", {}),
        "llm": {
            "temperature": cfg.get("llm", {}).get("temperature", 0.7),
            "active_provider": cfg.get("llm", {}).get("active_provider", "ollama"),
        },
        "tools": cfg.get("tools", {}),
    })


@app.put("/api/settings")
async def api_update_settings(request: Request):
    """Update settings. Accepts partial updates."""
    from sebastian.main import _load_config, _save_config
    body = await request.json()
    cfg = _load_config()

    if "tts" in body:
        cfg.setdefault("tts", {}).update(body["tts"])
    if "stt" in body:
        cfg.setdefault("stt", {}).update(body["stt"])
    if "wake_word" in body:
        cfg.setdefault("wake_word", {}).update(body["wake_word"])
    if "context" in body:
        cfg.setdefault("context", {}).update(body["context"])
    if "llm" in body:
        if "temperature" in body["llm"]:
            cfg.setdefault("llm", {})["temperature"] = body["llm"]["temperature"]
    if "tools" in body:
        cfg.setdefault("tools", {}).update(body["tools"])

    _save_config(cfg)
    return JSONResponse({"status": "ok"})


# ─── Mute APIs ───

@app.get("/api/mute")
async def api_get_mute():
    from sebastian.main import is_muted
    return JSONResponse({"muted": is_muted()})


@app.post("/api/mute")
async def api_toggle_mute():
    from sebastian.main import toggle_mute, is_muted
    toggle_mute()
    return JSONResponse({"muted": is_muted()})


# ─── WebSocket ───

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.append(ws)
    await ws.send_text(json.dumps({"type": "connected", "message": "Sebastian online."}))
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "chat":
                user_text = msg["text"]

                # "stop" typed in chat = abort everything
                from sebastian.main import _is_stop_command
                if _is_stop_command(user_text):
                    from sebastian.main import abort_all
                    abort_all()
                    await ws.send_text(json.dumps({"type": "response", "text": "Stopped."}))
                    continue

                from sebastian.main import _process_request, _Aborted
                loop = asyncio.get_event_loop()
                try:
                    response = await loop.run_in_executor(
                        None, _process_request, user_text,
                    )
                    from sebastian.main import _speak_streamed_if_unmuted
                    threading.Thread(target=_speak_streamed_if_unmuted, args=(response,), daemon=True).start()
                except _Aborted:
                    await ws.send_text(json.dumps({"type": "response", "text": "Stopped."}))
                except Exception as e:
                    await ws.send_text(json.dumps({"type": "response", "text": f"Error: {e}"}))

            elif msg.get("type") == "interrupt":
                from sebastian.main import abort_all
                abort_all()

    except WebSocketDisconnect:
        if ws in _clients:
            _clients.remove(ws)


def start_web_background(port: int = 7860) -> None:
    """Launch web UI in a daemon thread. Non-blocking."""
    global _port
    _port = port
    from sebastian.main import register_event_listener
    register_event_listener(_broadcast_to_ws)

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        loop.run_until_complete(server.serve())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
