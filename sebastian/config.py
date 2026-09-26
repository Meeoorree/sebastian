"""config.yaml, read and written in one place.

Always UTF-8: Windows' default encoding is cp1252, and code started without
start.bat (PYTHONUTF8=1) would otherwise misread the file. Saving escapes
non-ASCII characters as "\\uXXXX", so the file stays pure ASCII.
Note: saving drops comments (the web UI saves settings this way).
"""
from __future__ import annotations
from pathlib import Path

import yaml

PATH = Path(__file__).parent.parent / "config.yaml"


def load() -> dict:
    with open(PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save(cfg: dict) -> None:
    with open(PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=False)
