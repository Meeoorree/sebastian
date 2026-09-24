"""Regression: running `python -m sebastian.main` must not load sebastian.main twice
(a 2nd copy steals STT's abort flag and every recording aborts after one "stop")."""
import subprocess, sys
from pathlib import Path

SCRIPT = r'''
import sys, types, runpy, webbrowser, subprocess
def stub(name, **kw):
    m = types.ModuleType(name); m.__dict__.update(kw); sys.modules[name] = m
for n in ("msvcrt", "ollama", "sounddevice"): stub(n)
stub("openai", OpenAI=object)
stub("sebastian.tts", speak=lambda t: None, speak_streamed=lambda t: None, is_speaking=lambda: False, stop_speaking=lambda: None)
stub("sebastian.context", ContextManager=lambda: None); stub("sebastian.memory", Memory=lambda: None)
stub("sebastian.tools"); stub("sebastian.tools.router", TOOL_SCHEMAS=[], dispatch=None)
stub("sebastian.tools.macros", match_macro=lambda t: None, run_macro=None)
stub("sebastian.web", start_web_background=lambda port: None)
webbrowser.open = lambda u: None
def listen(cb):
    from sebastian.main import abort_all   # what web.py / wake.py do at runtime
    import sebastian.stt
    m = sys.modules["__main__"]
    print("OK" if abort_all is m.abort_all and sebastian.stt._abort_event is m._abort else "DOUBLE")
stub("sebastian.wake", listen_for_wake_word=listen)
runpy.run_module("sebastian.main", run_name="__main__", alter_sys=True)
'''


def test_main_module_loaded_once():
    root = Path(__file__).parent.parent
    out = subprocess.run([sys.executable, "-c", SCRIPT], cwd=root, capture_output=True, text=True)
    assert out.stdout.strip().endswith("OK"), out.stdout + out.stderr
