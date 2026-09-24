# Sebastian — a voice assistant for Windows

Say **"Sebastian"**, wait for "Yes?", and tell him what to do: open apps, click through UIs, search the web, control volume, run code. Speech recognition, the wake word and the voice all run on your own machine; only the "thinking" goes to an LLM of your choice (DeepSeek by default, or a local model through Ollama).

![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6)
![License](https://img.shields.io/badge/license-MIT-green)

## What he can do

- **Wake word + barge-in** — say "Sebastian" to start; say "shut up", "stop" or "enough" at any time to cut him off mid-sentence or mid-task. Both run offline on a tiny Vosk model restricted to those few phrases, with an echo guard so his own voice can't stop him.
- **Accurate speech recognition** — Whisper `large-v3-turbo` on the GPU (CPU fallback: `small.en`), biased toward your app names so "open VS Code" doesn't become "can we code".
- **Knows when you're done talking** — recording stops ~1.2 s after you stop, measured against your room's noise floor, not a fixed threshold.
- **33 desktop tools, chained agentically** — screen reading (OCR), clicking, typing, window focus, app launch (incl. Steam games), web search, weather, clipboard, volume, timers, files, sandboxed Python. Up to 15 tool calls per request.
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

The API key is read from the environment and never written to `config.yaml`.

## Using him

| Input | Action |
|---|---|
| "Sebastian" | Wake up and listen for a command |
| "Shut up" / "Stop" / "Enough" | Interrupt immediately (no wake word needed) |
| Esc | Abort everything |
| F2 | Type a command in the terminal |
| Insert | Mute / unmute voice |
| Web UI | Type commands, watch tool calls, change settings |

## Configuration (`config.yaml`)

| Section | Key settings |
|---|---|
| `wake_word` | `phrases` (wake), `stop_phrases` (barge-in) |
| `stt` | `model`, `device`, `prompt` (vocabulary hints — add your apps here), `silence_seconds`, `no_speech_timeout` |
| `llm` | `active_provider` and `providers` — any OpenAI-compatible API, or Ollama |
| `tts` | `voice`, `speed`, `name_phonemes` |

Using speakers instead of headphones and he stops himself? Remove the offending word from `stop_phrases`.

## Project layout

```
sebastian/
  main.py      pipeline: wake -> record -> transcribe -> LLM + tools -> speak
  wake.py      Vosk wake word and stop-phrase listener
  stt.py       recording (adaptive silence) + faster-whisper
  tts.py       Kokoro voice, interruptible streaming
  web.py       FastAPI + WebSocket dashboard
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
