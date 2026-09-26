# CLAUDE.md — Sebastian

Briefing for Claude Code. Read this before changing anything.

## What this is

Sebastian is a Windows voice assistant. You say "Sebastian", he answers "Yes?", records your command, transcribes it, lets an LLM act on it with 33 desktop tools, and speaks the answer back. Wake word, speech-to-text and text-to-speech run locally. The LLM is remote (DeepSeek by default) or local (Ollama).

The owner runs it daily on Windows 11 with an RTX 3070 (8 GB VRAM) and 16 GB RAM, often with WSL and many apps open. He is not a Python expert, so keep changes simple and explain them in plain language.

The project started from JarvisAi by PanPenek (MIT). The `LICENSE` must keep both copyright lines, and the README Acknowledgements line must stay.

## Commands

```bat
install.bat                  :: first-time setup: venv, deps, models (~1.7 GB)
start.bat                    :: run (sets HF_HOME, PYTHONUTF8=1, runs python -m sebastian.main)
.venv\Scripts\python -m pytest -q
```

The DeepSeek key comes from the `DEEPSEEK_API_KEY` environment variable. Never write it to `config.yaml`.

**Tests:** on Linux or in a cloud sandbox, only part of the suite can run:
- `test_tts.py` needs PortAudio.
- `test_tools.py::test_router_*` imports `pyautogui`, which needs a desktop session, so it is Windows-only.
- `test_memory.py` downloads a ChromaDB embedding model.

In the sandbox, run:
`pytest -q --ignore=tests/test_tts.py --ignore=tests/test_memory.py --deselect tests/test_tools.py::test_router_dispatch_unknown_tool --deselect tests/test_tools.py::test_router_dispatch_known_tool`
(75 tests should pass). Lightweight deps for this subset: `pip install pytest pytest-mock pyyaml numpy openai ollama fastapi uvicorn ddgs`. Audio, microphone, GPU and desktop control cannot be tested there. Mock them, and ask the owner to test on the real machine.

## Architecture

```
wake.py (thread: mic -> Vosk grammar)
   | "sebastian" while idle          | "shut up"/"stop" while busy
   v                                 v
main.handle_wake (worker thread)   main.abort_all()
   say "Yes?" -> pause wake mic -> stt.record_until_silence -> resume mic
   -> stt.transcribe_audio (faster-whisper) -> _process_request:
        macros.match_macro? -> run steps directly (no LLM)
        else LLM tool loop (<=15 calls) via tools/router.dispatch
        dangerous tool? -> stop, ask "Say yes"; the next input answers (confirm.py)
   -> tts.speak_streamed (Kokoro, interruptible)
web.py (uvicorn thread, 127.0.0.1:7860): dashboard + /ws chat; events via main._broadcast
keyboard thread (msvcrt): Esc = abort, F2 = type, Insert = mute
```

| File | Role |
|---|---|
| `sebastian/main.py` | Orchestrator: abort/mute state, event bus, one LLM tool loop (`_run_tool_loop`) with a small adapter per provider type (OpenAI-compatible, Ollama), system prompt |
| `sebastian/wake.py` | Vosk recognizer restricted to wake + stop phrases. Echo guard: ignores a stop word that appears in the sentence being spoken |
| `sebastian/stt.py` | Adaptive-silence recording; Whisper `large-v3-turbo` on CUDA, `small.en` CPU fallback; adds pip `nvidia/*/bin` DLL folders on Windows |
| `sebastian/tts.py` | Kokoro; `_pronounce()` rewrites the name to `[Sebastian](/phonemes/)`; `current_text()` feeds the echo guard |
| `sebastian/confirm.py` | "Say yes to go ahead": open question, yes/no matching, 60 s timeout |
| `sebastian/tools/router.py` | `TOOL_SCHEMAS` (sent to the LLM) and `dispatch(name, args)` |
| `sebastian/tools/macros.py` + `macros/macros.yaml` | Regex triggers checked before the LLM |
| `sebastian/memory.py`, `context.py` | SQLite + ChromaDB facts; sliding-window context with summarization |
| `setup_sebastian.py` | Model download with retries + GPU check (called by `install.bat`) |

## Must-know gotchas (each one caused a real bug)

1. **Single module instance.** `python -m sebastian.main` runs `main.py` as `__main__`. The alias at the top of `main.py` makes later `from sebastian.main import ...` calls (in web.py and wake.py) reuse that same module. Without it, a second copy replaces STT's abort event, and every recording aborts after the first "stop". Keep the alias, and keep `tests/test_single_module.py` green. When `main.py` gains a new import, add a stub for it in that test.
2. **Encoding.** Windows' default encoding is cp1252. Keep `config.yaml` pure ASCII (write non-ASCII as `"\uXXXX"` escapes) and open files with `encoding="utf-8"`. `start.bat` sets `PYTHONUTF8=1` as a safety net, but code launched any other way doesn't get it.
3. **Wake-word vocabulary.** Every phrase in `wake_word.phrases` / `stop_phrases` must exist in the Vosk small-en lexicon, otherwise Vosk silently drops it. With only a few words in the grammar, anything loud can match. `[unk]` catches everything else.
4. **Audio device sharing.** The wake listener must be paused (`pause_wake_mic`) while STT records. Both use the microphone.
5. **Silence detection** uses the measured noise floor (ignoring all-zero chunks from mic startup) plus 15% of the speech peak. Tune it with `stt.silence_seconds` and `stt.no_speech_timeout`; don't hard-code RMS values.
6. **Heavy dependencies:** torch (via Kokoro), CUDA DLLs and ~2 GB of models. Don't add dependencies without a strong reason. The owner's network is unreliable, so every download needs retries.
7. `config.yaml` is re-read on almost every call, and the web UI rewrites it with `yaml.dump`, which drops comments.
8. **Web UI origin guard.** `web.py` refuses any request whose `Origin` isn't `http://localhost:<port>` or `http://127.0.0.1:<port>`, and any `Host` other than those two names (DNS rebinding). This stops other websites from driving the LLM's tools through `/ws`. Don't remove it or add CORS. Opening the dashboard under another name (a LAN IP, a hostname) is refused by design. `tests/test_web.py` covers it.
9. **Confirmation for dangerous tools.** Tools in `tools.confirm` (default `run_python`, `write_file`, `power_command`, `kill_process`) never run from the LLM loop: `_run_tool_loop` stops and returns `confirm.ask(...)`, and only the owner's next input, checked at the top of `_process_request` via `confirm.resolve`, can run exactly that action. Never let tool output or LLM text reach `confirm.resolve`. The question text is built from the arguments (sanitized), not by the LLM. `tests/test_confirm.py` and `tests/test_main_loop.py` cover it.

## Review findings (prioritized backlog)

### P0: security

- **Prompt injection via typing.** `type_text` + `press_key` (e.g. `win+r`, type a command, `enter`) can still run commands without confirmation. They are not in `tools.confirm` by default because UI automation types constantly. Possible fix: confirm only risky sequences (a Run dialog, a terminal window focused).

### P1: bugs the owner has hit

(none open)

### P2: code health

- 8 copies of `_load_config` and 11 `open(_CONFIG_PATH)` calls without `encoding=` (10 reads, including 2 inline in `memory.py`, plus the write in `main.py`). Replace them with one `sebastian/config.py` (`load()`/`save()`, UTF-8), and keep the functions patchable for the tests.
- `llm.get_api_key` special-cases DeepSeek by URL. Replace that with an `api_key_env` field per provider in config, so any provider can read its key from the environment.
- `requirements.txt` is unpinned. Pin known-good versions (the owner's working venv: faster-whisper ≥1.1, ctranslate2 4.x, vosk 0.3.45, kokoro ≥0.9.4) to stop surprise breakage.
- There is no CI. Add a GitHub Actions `windows-latest` job running the portable subset of pytest.

### P3: nice to have

- A per-user app map in config (e.g. `apps: {vscode: "D:\\Microsoft VS Code\\Code.exe"}`) merged over `APP_MAP`.
- A custom openWakeWord model for "Sebastian", if Vosk false-triggers too often.
- Show the macros in the web UI and allow editing them there.

## Working rules

- Keep diffs small; one concern per commit/PR. Run the portable test subset before every commit.
- Bug fix = find the root cause, reproduce it in a test that fails first, then fix it.
- Never commit `.venv/`, `model_cache/`, `models/`, `sebastian/data/` (personal memory), `*.bak*`, or any API key.
- Windows is the target: use `os.startfile`, `winreg` and `msvcrt` only inside functions, never at import time.
- After changing behaviour, update `README.md` (and this file, if a gotcha or finding changes).
