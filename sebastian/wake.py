from __future__ import annotations
import json
from pathlib import Path
import threading
import time
import yaml

_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _ROOT / "config.yaml"


def _load_config():
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ─── Mic pause/resume for STT recording ───
# When STT needs to record, it pauses the wake mic so both don't fight
# over the same hardware device. Wake detection resumes after recording.

_mic_pause = threading.Event()


def pause_wake_mic() -> None:
    _mic_pause.set()


def resume_wake_mic() -> None:
    _mic_pause.clear()


def _matches(text: str, phrases: list[str]) -> str | None:
    """Return the phrase found in text (whole words), or None."""
    padded = f" {text} "
    for p in phrases:
        if f" {p} " in padded:
            return p
    return None


def _is_echo(phrase: str) -> bool:
    """True if the stop phrase is in what the assistant is saying right now
    (the speakers leaking into the mic), so we don't stop ourselves."""
    from sebastian.tts import is_speaking, current_text
    return is_speaking() and phrase in current_text().lower()


def listen_for_wake_word(callback) -> None:
    """
    Continuously listen with a small offline Vosk recognizer restricted to a
    few phrases. Blocking — runs forever in the calling thread.

    - IDLE: wake phrase ("hey sebastian") → start callback (listen for command)
    - BUSY: stop phrase ("shut up", "stop", ...) → abort current speech/task
    """
    import pyaudio
    from vosk import Model, KaldiRecognizer, SetLogLevel

    cfg = _load_config()["wake_word"]
    wake = [p.lower() for p in cfg["phrases"]]
    stop = [p.lower() for p in cfg["stop_phrases"]]
    chunk = cfg.get("chunk_size", 1600)  # 100 ms at 16 kHz

    SetLogLevel(-1)
    model_path = _ROOT / cfg["vosk_model"]
    if not model_path.exists():
        raise SystemExit(f"Vosk model not found at {model_path}. Run setup_sebastian.bat first.")
    model = Model(str(model_path))
    # Restricting the vocabulary is what makes a tiny model accurate here:
    # anything else is mapped to [unk] instead of being forced into a phrase.
    grammar = json.dumps(sorted(set(wake + stop)) + ["[unk]"])
    rec = KaldiRecognizer(model, 16000, grammar)

    audio = pyaudio.PyAudio()
    mic = audio.open(format=pyaudio.paInt16, channels=1, rate=16000,
                     input=True, frames_per_buffer=chunk)

    busy = threading.Lock()
    ignore_until = 0.0

    print(f"[{cfg.get('name', 'Sebastian')}] Listening for wake word...")
    try:
        while True:
            if _mic_pause.is_set():
                if mic.is_active():
                    mic.stop_stream()
                while _mic_pause.is_set():
                    time.sleep(0.05)
                mic.start_stream()
                rec.Reset()
                continue

            try:
                data = mic.read(chunk, exception_on_overflow=False)
            except Exception:
                time.sleep(0.05)
                continue

            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "")
            else:
                text = json.loads(rec.PartialResult()).get("partial", "")
            if not text or time.time() < ignore_until:
                continue

            if busy.locked():
                phrase = _matches(text, stop)
                if phrase and not _is_echo(phrase):
                    rec.Reset()
                    ignore_until = time.time() + 1.0
                    from sebastian.main import abort_all
                    abort_all()
                    print(f"[Voice] Stopped by \"{phrase}\".")
            elif _matches(text, wake):
                rec.Reset()
                ignore_until = time.time() + 1.5

                def _run():
                    with busy:
                        callback()

                threading.Thread(target=_run, daemon=True).start()
    finally:
        mic.stop_stream()
        mic.close()
        audio.terminate()
