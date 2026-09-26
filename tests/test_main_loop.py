"""The LLM tool loop in main.py, with audio, desktop and memory stubbed out."""
import importlib
import sys
import types
from types import SimpleNamespace

import pytest


class _Context:
    def __init__(self):
        self.messages = []

    def add(self, role, text):
        self.messages.append({"role": role, "content": text})

    def get_messages(self):
        return list(self.messages)


class _Memory:
    def search_facts(self, text):
        return []

    def extract_and_store_facts(self, response, user_text):
        pass


@pytest.fixture
def main(monkeypatch):
    def stub(name, **kw):
        m = types.ModuleType(name)
        m.__dict__.update(kw)
        monkeypatch.setitem(sys.modules, name, m)

    stub("msvcrt")
    stub("sounddevice")
    stub("sebastian.tts", speak=lambda t: None, speak_streamed=lambda t: None,
         is_speaking=lambda: False, stop_speaking=lambda: None)
    stub("sebastian.wake", listen_for_wake_word=None)
    stub("sebastian.context", ContextManager=_Context)
    stub("sebastian.memory", Memory=_Memory)
    stub("sebastian.tools.router", TOOL_SCHEMAS=[], dispatch=None)
    stub("sebastian.tools.macros", match_macro=lambda t: None, run_macro=None)
    monkeypatch.delitem(sys.modules, "sebastian.main", raising=False)
    m = importlib.import_module("sebastian.main")
    monkeypatch.setattr(m, "_play_beep", lambda: None)
    yield m
    sys.modules.pop("sebastian.main", None)


def _call(name, args, id="call_1"):
    return SimpleNamespace(id=id, function=SimpleNamespace(name=name, arguments=args))


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls,
                           model_dump=lambda: {"role": "assistant", "content": content})


def _use(main, monkeypatch, ptype, replies, tools_cfg=None):
    """Make the active provider answer with `replies`, one per LLM call.
    Returns (sent, ran): the message lists sent to the LLM and the tools run."""
    replies, sent, ran = list(replies), [], []
    cfg = {"llm": {"active_provider": "p", "temperature": 0.5,
                   "providers": {"p": {"type": ptype, "model": "m", "base_url": "http://x"}}},
           "tools": tools_cfg or {}}
    monkeypatch.setattr(main, "_load_config", lambda: cfg)
    monkeypatch.setattr(main, "get_api_key", lambda p: "key")

    def reply(messages):
        sent.append([dict(m) if isinstance(m, dict) else m for m in messages])
        return replies.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=reply(kw["messages"]))]))))
    monkeypatch.setattr(main, "_get_openai_client", lambda url, key: client)
    monkeypatch.setattr(main.ollama, "chat", lambda **kw: SimpleNamespace(message=reply(kw["messages"])))

    def dispatch(name, args):
        ran.append((name, args))
        return f"{name} ok"
    monkeypatch.setattr(main, "dispatch", dispatch)
    return sent, ran


@pytest.mark.parametrize("ptype,args", [("openai", '{"level": 30}'), ("ollama", {"level": 30})])
def test_tool_call_then_answer(main, monkeypatch, ptype, args):
    sent, ran = _use(main, monkeypatch, ptype, [
        _msg(tool_calls=[_call("set_volume", args)]),
        _msg(content="<think>hmm</think>Volume set to 30."),
    ])
    assert main._call_llm([{"role": "user", "content": "volume 30"}]) == "Volume set to 30."
    assert ran == [("set_volume", {"level": 30})]
    tool_msg = sent[1][-1]
    assert tool_msg["role"] == "tool" and tool_msg["content"] == "set_volume ok"
    if ptype == "openai":
        assert tool_msg["tool_call_id"] == "call_1"
    else:
        assert tool_msg["name"] == "set_volume"


def test_loop_stops_after_max_tool_calls(main, monkeypatch):
    replies = [_msg(tool_calls=[_call("get_volume", "{}")])] * (main._MAX_TOOL_LOOPS + 5)
    _, ran = _use(main, monkeypatch, "openai", replies)
    assert main._call_llm([{"role": "user", "content": "loop"}]) == "Done."
    assert len(ran) == main._MAX_TOOL_LOOPS
