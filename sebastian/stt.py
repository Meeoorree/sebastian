import os
import sys
from pathlib import Path
import yaml
import numpy as np


def _add_cuda_dlls() -> None:
    """Make pip-installed CUDA libs (nvidia-cublas-cu12, nvidia-cudnn-cu12)
    visible on Windows so Whisper can run on the GPU."""
    if os.name != "nt":
        return
    for d in (Path(sys.prefix) / "Lib" / "site-packages" / "nvidia").glob("*/bin"):
        os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]
        os.add_dll_directory(str(d))


_add_cuda_dlls()

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def _load_config():
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)

_model = None
_model_device = None  # track what device the model is on

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore

def _get_model(force_cpu=False):
    global _model, _model_device
    if _model is not None and not force_cpu:
        return _model
    cfg = _load_config()
    stt = cfg["stt"]
    device = "cpu" if force_cpu else stt["device"]
    compute_type = "int8" if force_cpu else stt["compute_type"]
    name = stt["cpu_model"] if device == "cpu" else stt["model"]
    try:
        _model = WhisperModel(name, device=device, compute_type=compute_type)
        _model_device = device
        print(f"[STT] Loaded {name} on {device}")
    except Exception as e:
        if device != "cpu":
            print(f"[STT] {device} failed to load ({e}), falling back to CPU")
            _model = WhisperModel(stt["cpu_model"], device="cpu", compute_type="int8")
            _model_device = "cpu"
            print(f"[STT] Loaded {stt['cpu_model']} on cpu")
        else:
            raise
    return _model


def _run(model, audio) -> str:
    # vad_filter drops silence (stops Whisper hallucinating "You");
    # initial_prompt biases it toward your app names ("VS Code", not "we code").
    segments, _ = model.transcribe(
        audio, beam_size=5, language="en", vad_filter=True,
        initial_prompt=_load_config()["stt"].get("prompt"),
    )
    return " ".join(seg.text.strip() for seg in segments).strip()

def transcribe_audio(audio: np.ndarray) -> str:
    """Transcribe a float32 numpy audio array (16kHz mono) to text."""
    try:
        return _run(_get_model(), audio)
    except Exception as e:
        # If CUDA worked for loading but fails during inference, retry on CPU
        if _model_device != "cpu":
            print(f"[STT] {_model_device} transcription failed ({e}), reloading on CPU")
            try:
                return _run(_get_model(force_cpu=True), audio)
            except Exception as e2:
                print(f"[STT] CPU transcription also failed: {e2}")
                return ""
        print(f"[STT] Transcription failed: {e}")
        return ""

# Global abort event — set by main.py so recording can be interrupted
_abort_event = None

def set_abort_event(event) -> None:
    """Register the global abort event so recording checks it."""
    global _abort_event
    _abort_event = event

def record_until_silence(sample_rate: int = 16000, max_seconds: int = 30) -> np.ndarray:
    """Record until you stop talking. Returns float32 audio.
    "Speech" = louder than 3x the room's noise floor (measured on the fly), so a
    fan or background hum no longer keeps the recording open.
    Gives up if you say nothing for no_speech_timeout seconds. Esc aborts."""
    import sounddevice as sd

    cfg = _load_config()["stt"]
    chunk = int(sample_rate * 0.1)  # 100 ms
    silence_needed = int(cfg.get("silence_seconds", 1.2) / 0.1)
    no_speech_chunks = int(cfg.get("no_speech_timeout", 6) / 0.1)
    recording, silent, heard_speech, noise, peak = [], 0, False, None, 0.0

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32") as stream:
        while True:
            if _abort_event and _abort_event.is_set():
                print("[STT] Recording aborted.")
                break
            data, _ = stream.read(chunk)
            flat = data.flatten()
            recording.append(flat)
            rms = float(np.sqrt(np.mean(flat ** 2)))
            if rms > 1e-4:  # skip the all-zero chunks a mic returns while starting up
                noise = rms if noise is None else min(noise, rms)
            floor = noise or 0.0
            # Silence = back near the noise floor OR well below how loud you were talking.
            loud = rms > max(0.01, floor * 3, peak * 0.15)
            if loud:
                if not heard_speech:
                    print(f"[STT] Speech detected (rms={rms:.4f}, noise={floor:.4f})")
                heard_speech, silent, peak = True, 0, max(peak, rms)
            elif heard_speech:
                silent += 1
                if silent >= silence_needed:
                    print("[STT] Silence detected, stopping recording.")
                    break
            elif len(recording) >= no_speech_chunks:
                print("[STT] No speech heard, giving up.")
                return np.zeros(chunk, dtype=np.float32)
            if len(recording) * chunk >= max_seconds * sample_rate:
                print(f"[STT] Max recording time reached ({max_seconds}s)")
                break

    if not recording:
        return np.zeros(chunk, dtype=np.float32)
    return np.concatenate(recording)
