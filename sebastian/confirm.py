"""Ask the owner before running dangerous tools.

Text from web pages, files and the screen goes into the LLM's context, so a
malicious page could talk the model into running code or shutting the PC down.
Tools listed in config `tools.confirm` therefore don't run straight away:
Sebastian asks, and only the owner's next reply (voice, F2 or web chat) can say
yes. The LLM never sees the question as something it could answer, and a yes
runs exactly the action that was asked about.
"""
from __future__ import annotations
import json
import re
import threading
import time
from pathlib import PureWindowsPath

DEFAULT_TOOLS = ["run_python", "write_file", "power_command", "kill_process"]
TIMEOUT = 60  # seconds a question stays open

_YES = {"yes", "yeah", "yep", "sure", "ok", "okay", "confirm", "confirmed",
        "do it", "go ahead", "go", "yes please", "\u0434\u0430"}  # last one: Russian "da"
_NO = {"no", "nope", "cancel", "stop", "don't", "dont", "do not", "never mind",
       "nevermind", "no thanks", "\u043d\u0435\u0442"}  # last one: Russian "net"

_lock = threading.Lock()
_pending: dict | None = None  # {"name", "args", "at"}


def needs_confirmation(name: str, tools_cfg: dict | None) -> bool:
    """True if `name` is in config `tools.confirm` (a missing key means the defaults)."""
    listed = (tools_cfg or {}).get("confirm")
    return name in (DEFAULT_TOOLS if listed is None else listed)


def _clean(value, limit: int = 40) -> str:
    """Keep a tool argument short and plain before it is read aloud."""
    return re.sub(r"[^\w .\-]", "", str(value))[:limit].strip() or "something"


def _describe(name: str, args: dict) -> str:
    if name == "run_python":
        return "run a Python script on your PC. The code is in the console and the dashboard"
    if name == "write_file":
        return f"write the file {_clean(PureWindowsPath(str(args.get('path', ''))).name)}"
    if name == "power_command":
        action = str(args.get("action", "")).lower().strip()
        return {"shutdown": "shut down the PC", "restart": "restart the PC",
                "sleep": "put the PC to sleep"}.get(action, f"run the power command {_clean(action)}")
    if name == "kill_process":
        return f"force-close {_clean(args.get('name', ''))}"
    return f"use the tool {name}"


def detail(name: str, args: dict) -> str:
    """The full action, for the console and the dashboard."""
    if name == "run_python":
        return str(args.get("code", ""))
    return json.dumps(args, indent=2, ensure_ascii=False)


def ask(name: str, args: dict) -> str:
    """Remember the action and return the question to put to the owner."""
    global _pending
    with _lock:
        _pending = {"name": name, "args": args, "at": time.monotonic()}
    return f"I'd like to {_describe(name, args)}. Say yes to go ahead, or no to cancel."


def is_pending() -> bool:
    with _lock:
        return _pending is not None and time.monotonic() - _pending["at"] <= TIMEOUT


def cancel() -> None:
    global _pending
    with _lock:
        _pending = None


def _is(words: str, answers: set[str]) -> bool:
    """'yes', 'Yes.', 'Sebastian, yes', 'okay, go ahead' all count; 'yes but first...' does not."""
    words = re.sub(r"[^\w' ]", " ", words.lower().replace("\u2019", "'")).split()
    if words[:1] == ["sebastian"]:
        words = words[1:]
    text = " ".join(words)
    if text in answers:
        return True
    return bool(words) and words[0] in answers and " ".join(words[1:]) in answers


def resolve(text: str):
    """Match the owner's reply against the open question, and close the question.

    Returns ("yes", (name, args)), ("no", None), or (None, None) when no question
    was open (or it timed out) or the reply was something else. Something else
    cancels the question, so a later stray "yes" can't run an old action.
    """
    global _pending
    with _lock:
        pending, _pending = _pending, None
    if pending is None or time.monotonic() - pending["at"] > TIMEOUT:
        return None, None
    if _is(text, _YES):
        return "yes", (pending["name"], pending["args"])
    if _is(text, _NO):
        return "no", None
    return None, None
