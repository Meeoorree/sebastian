"""config.yaml is read and written in one place, as UTF-8 (Windows' default is cp1252)."""
import builtins
import re
from pathlib import Path

from sebastian import config

ROOT = Path(__file__).parent.parent


def test_only_config_py_opens_config_yaml():
    offenders = [str(p.relative_to(ROOT)) for p in (ROOT / "sebastian").rglob("*.py")
                 if p.name != "config.py"
                 and re.search(r"_CONFIG_PATH|['\"]config\.yaml['\"]", p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_load_and_save_use_utf8(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PATH", tmp_path / "config.yaml")
    encodings, real_open = [], builtins.open

    def spy(*args, **kwargs):
        encodings.append(kwargs.get("encoding"))
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    config.save({"tts": {"name_phonemes": "sˌɛbɑstiˈɑn"}, "stt": {"prompt": "открой"}})
    loaded = config.load()
    assert encodings == ["utf-8", "utf-8"]
    assert loaded["tts"]["name_phonemes"] == "sˌɛbɑstiˈɑn"
    assert loaded["stt"]["prompt"] == "открой"


def test_saved_file_stays_ascii(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PATH", tmp_path / "config.yaml")
    config.save({"stt": {"prompt": "Yandex Браузер"}, "llm": {"temperature": 0.7}})
    (tmp_path / "config.yaml").read_bytes().decode("ascii")  # raises if not pure ASCII
    assert list(config.load()) == ["stt", "llm"]  # key order kept


def test_repo_config_is_ascii_and_loads():
    (ROOT / "config.yaml").read_bytes().decode("ascii")
    assert "llm" in config.load()
