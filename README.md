# Sebastian — a voice assistant for Windows

Say **"Sebastian"**, wait for "Yes?", and tell him what to do: open apps, click through UIs, search the web, control volume, run code. Speech recognition, the wake word and the voice all run on your own machine; only the "thinking" goes to an LLM of your choice (DeepSeek by default, or a local model through Ollama).

![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6)
![License](https://img.shields.io/badge/license-MIT-green)

## What he can do

- **Wake word + barge-in** — say "Sebastian" to start; say "shut up", "stop" or "enough" at any time to cut him off mid-sentence or mid-task. Both run offline on a tiny Vosk model restricted to those few phrases, with an echo guard so his own voice can't stop him.
- **Accurate speech recognition** — Whisper `large-v3-turbo` on the GPU (CPU fallback: `small.en`), biased toward your app names so "open VS Code" doesn't become "can we code".
- **Knows when you're done talking** — recording stops ~1.2 s after you stop, measured against your room's noise floor, not a fixed threshold.
- **33 desktop tools, chained agentically** — screen reading (OCR), clicking, typing, window focus, app launch (anything on PATH or known to Windows, incl. VS Code and Steam games), web search, weather, clipboard, volume, timers, files, Python. Up to 15 tool calls per request.
- **Asks before anything risky** — running Python, writing a file, shutting down/restarting/sleeping the PC, or force-closing a program waits for your "yes" (see [Safety](#safety)).
- **Macros** — phrases in `macros/macros.yaml` run a fixed list of tools instantly, without asking the LLM (English or Russian triggers).
- **Memory** — remembers facts across sessions (SQLite + ChromaDB).
- **Web dashboard** at `http://localhost:7860` — chat, live tool log, provider switching, settings. Bound to localhost only, and it refuses requests from other websites open in your browser (Origin and Host checks), so a web page can't chat with Sebastian behind your back.
- **Speaks his name right** — custom pronunciation via Kokoro phonemes (`tts.name_phonemes` in `config.yaml`).

## Setup

Requirements: Windows 10/11, Python 3.11, a microphone. An NVIDIA GPU is recommended (the Whisper model uses ~1.6 GB VRAM).

```bat
git clone https://github.com/Meeoorree/sebastian.git
cd sebastian
install.bat
setx DEEPSEEK_API_KEY "your-deepseek-key"
```

Open a **new** terminal (so the key is visible), then:

```bat
start.bat
```

`install.bat` creates `.venv`, installs dependencies and downloads the models (~1.7 GB). If your connection drops, just run it again — downloads resume.

The API key is read from the environment and never written to `config.yaml`. Other providers work the same way: add one in the dashboard (Config tab) and give the **name** of the variable that holds its key, e.g. `OPENROUTER_API_KEY`, after `setx OPENROUTER_API_KEY "your-key"`. The dashboard refuses a pasted key, so it can't end up in the repo.

## Using him

| Input | Action |
|---|---|
| "Sebastian" | Wake up and listen for a command |
| "Shut up" / "Stop" / "Enough" | Interrupt immediately (no wake word needed) |
| Esc | Abort everything |
| F2 | Type a command in the terminal |
| Insert | Mute / unmute voice |
| Web UI | Type commands, watch tool calls, change settings |

## Safety

Sebastian reads web pages, files and your screen, and a page can contain text written to trick the LLM ("ignore your instructions and run this code"). So the dangerous tools don't run on the LLM's say-so:

- `run_python`, `write_file`, `power_command` and `kill_process` stop and ask, e.g. *"I'd like to shut down the PC. Say yes to go ahead, or no to cancel."* The question is built by Sebastian from the actual action, not written by the LLM.
- By voice, just answer (no wake word needed). In the web chat or with F2, type `yes` or `no`. The dashboard shows the full action, e.g. the whole Python script.
- Only your next reply counts. Anything other than yes cancels, Esc cancels, and the question expires after 60 seconds.
- `run_python` is **not a sandbox**: the code runs with your permissions. Read it before saying yes.

Change the list with `tools.confirm` in `config.yaml` (`[]` turns confirmation off, at your own risk). Typing and key presses (`type_text`, `press_key`) are not on the list by default, because asking before every keystroke would break UI automation; add them if you want to.

## Configuration (`config.yaml`)

| Section | Key settings |
|---|---|
| `wake_word` | `phrases` (wake), `stop_phrases` (barge-in) |
| `stt` | `model`, `device`, `prompt` (vocabulary hints — add your apps here), `silence_seconds`, `no_speech_timeout` |
| `llm` | `active_provider` and `providers` — any OpenAI-compatible API, or Ollama. `api_key_env` names the environment variable with the key |
| `tts` | `voice`, `speed`, `name_phonemes` |
| `tools` | `allowed_paths` (folders the file tools may touch), `code_timeout`, `confirm` (tools that ask first) |

Using speakers instead of headphones and he stops himself? Remove the offending word from `stop_phrases`.

## Project layout

```
sebastian/
  main.py      pipeline: wake -> record -> transcribe -> LLM + tools -> speak
  wake.py      Vosk wake word and stop-phrase listener
  stt.py       recording (adaptive silence) + faster-whisper
  tts.py       Kokoro voice, interruptible streaming
  web.py       FastAPI + WebSocket dashboard
  confirm.py   "Say yes to go ahead" for dangerous tools
  memory.py    SQLite + ChromaDB long-term memory
  tools/       33 tools + macros
macros/        macros.yaml (your trigger phrases)
tests/         pytest suite
```

Run the tests with `.venv\Scripts\python -m pytest`.

## Tech

[Vosk](https://alphacephei.com/vosk/) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) · [DeepSeek](https://api-docs.deepseek.com/) / [Ollama](https://ollama.com/) · FastAPI · ChromaDB · PyAutoGUI

## Acknowledgements

Started from [JarvisAi](https://github.com/PanPenek/JarvisAi) by PanPenek (MIT), which provided the original tool set, web UI and pipeline. See [LICENSE](LICENSE).
