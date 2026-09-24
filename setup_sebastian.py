"""One-time download of the models Sebastian needs. Safe to re-run."""
import io
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
VOSK = "vosk-model-small-en-us-0.15"


def retry(what, fn, tries=6):
    for i in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:  # flaky network: back off and try again
            print(f"  {what}: attempt {i} failed ({e})")
            time.sleep(3 * i)
    raise SystemExit(f"Could not download {what}. Check your connection and re-run.")


dest = ROOT / "models"
if (dest / VOSK).exists():
    print(f"[1/2] Wake/stop word model already present.")
else:
    print(f"[1/2] Downloading wake/stop word model (~40 MB)...")
    url = f"https://alphacephei.com/vosk/models/{VOSK}.zip"
    data = retry("Vosk model", lambda: urllib.request.urlopen(url, timeout=60).read())
    zipfile.ZipFile(io.BytesIO(data)).extractall(dest)

print("[2/2] Downloading Whisper large-v3-turbo (~1.6 GB) and checking the GPU...")
import sebastian.stt  # noqa: E402  (adds the CUDA DLL folders)
from faster_whisper import WhisperModel, download_model  # noqa: E402
import numpy as np  # noqa: E402

path = retry("Whisper large-v3-turbo", lambda: download_model("large-v3-turbo"))
retry("Whisper small.en (CPU fallback)", lambda: download_model("small.en"))
try:
    m = WhisperModel(path, device="cuda", compute_type="float16")
    list(m.transcribe(np.zeros(16000, dtype=np.float32), language="en")[0])
    print("GPU transcription OK.")
except Exception as e:
    print(f"WARNING: GPU not usable ({e}). Sebastian will fall back to small.en on CPU.")

words = dest / VOSK / "graph" / "words.txt"
if words.exists() and "sebastian" not in words.read_text().split():
    print("WARNING: 'sebastian' is not in the Vosk vocabulary; the wake word will not work.")
print("\nAll set. Run start.bat and say \"Sebastian\".")
