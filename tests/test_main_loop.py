"""The LLM tool loop in main.py, with audio, desktop and memory stubbed out."""
import importlib
import sys
import types
from types import SimpleNamespace

import pytest

from sebastian import confirm


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
    confirm.cancel()
    yield m
    confirm.cancel()
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


# --- dangerous tools wait for the owner's yes (prompt-injection guard) ---

CODE = {"code": "print(42)"}


def test_dangerous_tool_waits_for_owner_yes(main, monkeypatch):
    sent, ran = _use(main, monkeypatch, "openai", [
        _msg(tool_calls=[_call("run_python", '{"code": "print(42)"}')]),
        _msg(content="It printed 42."),
    ])
    question = main._process_request("run some code")
    assert "Python" in question and "yes" in question
    assert ran == [] and len(sent) == 1  # nothing ran, and the LLM got no chance to answer itself

    assert main._process_request("Yes.") == "It printed 42."
    assert ran == [("run_python", CODE)]
    assert "run_python ok" in sent[1][-1]["content"]  # the LLM sees the result to report it


def test_no_cancels_dangerous_tool(main, monkeypatch):
    _, ran = _use(main, monkeypatch, "openai", [
        _msg(tool_calls=[_call("power_command", '{"action": "shutdown"}')]),
    ])
    assert "shut down the PC" in main._process_request("turn off the computer")
    assert "won't" in main._process_request("no")
    assert ran == []


def test_other_reply_cancels_and_is_handled_normally(main, monkeypatch):
    _, ran = _use(main, monkeypatch, "openai", [
        _msg(tool_calls=[_call("kill_process", '{"name": "chrome"}')]),
        _msg(content="Sunny."),
        _msg(content="Yes to what?"),
    ])
    main._process_request("close chrome")
    assert main._process_request("what's the weather") == "Sunny."
    assert main._process_request("yes") == "Yes to what?"  # the old question is gone
    assert ran == []


def test_safe_tools_run_before_the_question(main, monkeypatch):
    _, ran = _use(main, monkeypatch, "openai", [
        _msg(tool_calls=[_call("read_screen", "{}", "a"), _call("write_file", '{"path": "x", "content": "y"}', "b")]),
    ])
    assert "write the file x" in main._process_request("save the screen text")
    assert ran == [("read_screen", {})]


def test_confirm_list_comes_from_config(main, monkeypatch):
    _, ran = _use(main, monkeypatch, "openai", [
        _msg(tool_calls=[_call("run_python", '{"code": "print(42)"}')]),
        _msg(content="42"),
    ], tools_cfg={"confirm": []})
    assert main._process_request("run some code") == "42"
    assert ran == [("run_python", CODE)]


def test_abort_cancels_open_question(main, monkeypatch):
    _use(main, monkeypatch, "openai", [_msg(tool_calls=[_call("run_python", '{"code": "1"}')])])
    main._process_request("run some code")
    main.abort_all()
    assert not confirm.is_pending()


def test_voice_answer_needs_no_wake_word(main, monkeypatch):
    _, ran = _use(main, monkeypatch, "openai", [
        _msg(tool_calls=[_call("kill_process", '{"name": "chrome"}')]),
        _msg(content="Chrome is closed."),
    ])
    heard = iter(["close chrome", "yes"])
    spoken = []
    monkeypatch.setattr(main, "_listen", lambda: next(heard))
    monkeypatch.setattr(main, "_speak_streamed_if_unmuted", spoken.append)
    main._handle_wake_inner()
    assert ran == [("kill_process", {"name": "chrome"})]
    assert "force-close chrome" in spoken[0] and spoken[1] == "Chrome is closed."


def test_voice_silence_cancels_question(main, monkeypatch):
    _, ran = _use(main, monkeypatch, "openai", [_msg(tool_calls=[_call("kill_process", '{"name": "chrome"}')])])
    heard = iter(["close chrome", ""])
    said = []
    monkeypatch.setattr(main, "_listen", lambda: next(heard))
    monkeypatch.setattr(main, "_speak_if_unmuted", said.append)
    main._handle_wake_inner()
    assert ran == [] and not confirm.is_pending() and said[-1] == "Okay, cancelled."
