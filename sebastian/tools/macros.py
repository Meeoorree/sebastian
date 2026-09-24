"""User-defined trigger macros, loaded from macros/macros.yaml.

A macro is matched against the raw user text *before* the LLM is consulted
(see sebastian/main.py::_process_request). That makes phrases like "I want beer"
fire deterministically and instantly instead of relying on the model to pick
the right tool. Steps are dispatched through the same router as everything else.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

_YAML_PATH = Path(__file__).resolve().parents[2] / "macros" / "macros.yaml"

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            with open(_YAML_PATH, encoding="utf-8") as f:
                _cache = yaml.safe_load(f) or {}
        except FileNotFoundError:
            _cache = {}
    return _cache


def reload_macros() -> dict:
    """Drop the cache so edits to macros.yaml take effect immediately."""
    global _cache
    _cache = None
    return _load()


def match_macro(text: str) -> dict | None:
    """Return the first macro whose trigger pattern matches the user's text."""
    if not text or not text.strip():
        return None
    for macro in _load().get("macros", []) or []:
        for pattern in macro.get("triggers", []) or []:
            if re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE):
                return macro
    return None


def run_macro(macro: dict, on_step=None) -> list[str]:
    """Execute a macro's steps in order. Returns one result string per step."""
    from sebastian.tools.router import dispatch

    results = []
    for step in macro.get("steps", []) or []:
        tool = step["tool"]
        args = step.get("args") or {}
        try:
            result = str(dispatch(tool, args))
        except Exception as e:  # never let a macro crash the voice loop
            result = f"{tool} failed: {e}"
        results.append(result)
        if on_step is not None:
            on_step(tool, args, result)
    return results
