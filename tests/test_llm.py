from unittest.mock import patch, MagicMock

import pytest

from sebastian.llm import chat, get_api_key

DEEPSEEK = {"type": "openai", "model": "deepseek-flash", "base_url": "https://api.deepseek.com"}


def _cfg(provider):
    return {"llm": {"active_provider": "p", "temperature": 0.7, "providers": {"p": provider}}}


def _openai_reply(text):
    client = MagicMock()
    client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content=text))]
    return client


def test_deepseek_key_comes_from_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    assert get_api_key(DEEPSEEK) == "sk-test"


def test_missing_deepseek_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        get_api_key(DEEPSEEK)


def test_openai_compatible_provider(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    client = _openai_reply("Good morning.")
    with patch("sebastian.llm._load_config", return_value=_cfg(DEEPSEEK)), \
         patch("openai.OpenAI", return_value=client) as ctor:
        assert chat([{"role": "user", "content": "hi"}]) == "Good morning."
    assert ctor.call_args.kwargs["api_key"] == "sk-test"


def test_provider_failure_returns_error_text_instead_of_crashing(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    with patch("sebastian.llm._load_config", return_value=_cfg(DEEPSEEK)), \
         patch("openai.OpenAI", side_effect=Exception("offline")):
        assert chat([{"role": "user", "content": "hi"}]).startswith("[LLM error: offline")


def test_ollama_provider():
    reply = MagicMock(message=MagicMock(content="from ollama"))
    with patch("sebastian.llm._load_config", return_value=_cfg({"type": "ollama", "model": "qwen3:4b"})), \
         patch("ollama.chat", return_value=reply) as call:
        assert chat([{"role": "user", "content": "hi"}]) == "from ollama"
    assert call.call_args.kwargs["model"] == "qwen3:4b"


OPENROUTER = {"type": "openai", "model": "x", "base_url": "https://openrouter.ai/api/v1",
              "api_key_env": "OPENROUTER_API_KEY"}


def test_any_provider_reads_its_key_from_the_named_variable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert get_api_key(OPENROUTER) == "sk-or-test"


def test_missing_key_names_the_variable(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        get_api_key(OPENROUTER)


def test_local_server_needs_no_key():
    assert get_api_key({"type": "openai", "base_url": "http://localhost:1234/v1"}) == "lm-studio"
