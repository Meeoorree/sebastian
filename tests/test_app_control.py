"""open_app: find programs the way Windows does, and don't touch winreg at import time."""
import importlib
import sys

import pytest

CODE_CMD = r"D:\Microsoft VS Code\bin\code.CMD"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setitem(sys.modules, "winreg", None)  # importing must not need it
    monkeypatch.delitem(sys.modules, "sebastian.tools.app_control", raising=False)
    mod = importlib.import_module("sebastian.tools.app_control")
    yield mod
    sys.modules.pop("sebastian.tools.app_control", None)


@pytest.fixture
def launched(app, monkeypatch):
    """Record launches. Like Windows, Popen only finds a program by full path or as NAME.exe on PATH."""
    calls = []
    on_path = {"code": CODE_CMD, "notepad.exe": r"C:\Windows\notepad.exe"}

    def popen(args, **kw):
        if args[0] not in on_path.values():
            raise FileNotFoundError(2, "The system cannot find the file specified")
        calls.append(("popen", args))

    def startfile(target):
        if target == "nothing-like-this":
            raise FileNotFoundError(2, "The system cannot find the file specified")
        calls.append(("startfile", target))

    monkeypatch.setattr(app.subprocess, "Popen", popen)
    monkeypatch.setattr(app.shutil, "which", lambda name: on_path.get(name))
    monkeypatch.setattr(app.os, "startfile", startfile, raising=False)
    monkeypatch.setattr(app.os.path, "isfile", lambda p: p in on_path.values())
    return calls


def test_import_does_not_need_winreg(app):
    assert callable(app.open_app)  # the fixture imported it with winreg blocked


def test_vscode_resolves_code_cmd(app, launched):
    # The owner's bug: Popen(["code"]) -> [WinError 2], because "code" is code.cmd.
    assert app.open_app("vscode") == "Opening vscode."
    assert launched == [("popen", [CODE_CMD])]


def test_exe_on_path(app, launched):
    assert app.open_app("notepad") == "Opening notepad."
    assert launched == [("popen", [r"C:\Windows\notepad.exe"])]


def test_protocol_and_unknown_names_go_through_the_shell(app, launched):
    assert app.open_app("settings") == "Opening settings."  # ms-settings: is not a program
    assert app.open_app("obs") == "Opening obs."            # not in the map: let Windows find it
    assert launched == [("startfile", "ms-settings:"), ("startfile", "obs")]


def test_missing_program_reports_error(app, launched):
    assert app.open_app("nothing-like-this").startswith("Could not open nothing-like-this")


def test_steam_is_looked_up_only_when_opened(app, launched, monkeypatch):
    looked_up = []
    monkeypatch.setattr(app, "_steam_exe", lambda: looked_up.append(1) or r"E:\Steam\steam.exe")
    monkeypatch.setattr(app.os.path, "isfile", lambda p: p == r"E:\Steam\steam.exe")
    monkeypatch.setattr(app.subprocess, "Popen", lambda args, **kw: launched.append(("popen", args)))
    assert looked_up == []
    assert app.open_app("steam") == "Opening steam."
    assert looked_up == [1] and launched == [("popen", [r"E:\Steam\steam.exe"])]
