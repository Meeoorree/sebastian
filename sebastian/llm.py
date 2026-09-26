"""Lightweight LLM chat function for internal tasks (context summarization, etc.)."""
import os
from sebastian.config import load as _load_config


def get_api_key(provider: dict) -> str:
    """API key for an OpenAI-compatible provider.

    Keys live in environment variables, never in config.yaml (the repo is public):
    a provider names its variable with `api_key_env`, e.g. OPENROUTER_API_KEY.
    Local servers (LM Studio, ...) need no key.
    """
    env = provider.get("api_key_env")
    if not env and provider.get("base_url") == "https://api.deepseek.com":
        env = "DEEPSEEK_API_KEY"  # configs from before api_key_env existed
    if env:
        key = os.environ.get(env)
        if not key:
            raise RuntimeError(f"Set {env} in Windows before starting Sebastian")
        return key
    return provider.get("api_key") or "lm-studio"  # old configs; the web UI no longer writes keys


def chat(messages: list[dict]) -> str:
    """Send messages to the active LLM provider and return response text.

    Uses the same provider system as main.py — reads active_provider from config.
    Used for internal tasks like context summarization.
    """
    cfg = _load_config()
    llm_cfg = cfg.get("llm", {})
    temperature = llm_cfg.get("temperature", 0.7)
    active = llm_cfg.get("active_provider", "ollama")
    providers = llm_cfg.get("providers", {})
    provider = providers.get(active, {})
    ptype = provider.get("type", "ollama")

    if ptype == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=provider["base_url"],
                api_key=get_api_key(provider),
                timeout=15.0,
            )
            resp = client.chat.completions.create(
                model=provider["model"],
                messages=messages,
                temperature=temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"[LLM error: {e}]"

    # Ollama (default or fallback)
    import ollama
    ollama_cfg = providers.get("ollama", provider)
    model = ollama_cfg.get("model", "qwen3:8b")
    try:
        response = ollama.chat(model=model, messages=messages)
        return response.message.content or ""
    except Exception as e:
        return f"[LLM error: {e}]"
