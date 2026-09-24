# sebastian/tests/test_stt.py
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

STUB_CONFIG = {
    "stt": {"model": "turbo", "device": "cuda", "compute_type": "float16", "cpu_model": "small.en"}
}

def test_transcribe_returns_string():
    """transcribe_audio should return a string for valid audio."""
    with patch("sebastian.stt._load_config", return_value=STUB_CONFIG), \
         patch("sebastian.stt.WhisperModel") as mock_model_cls:
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = " hello world"
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_model_cls.return_value = mock_model
        # Reset module singleton so new mock takes effect
        import sebastian.stt as stt_mod
        stt_mod._model = None

        from sebastian.stt import transcribe_audio
        fake_audio = np.zeros(16000, dtype=np.float32)
        result = transcribe_audio(fake_audio)
        assert isinstance(result, str)

def test_transcribe_strips_whitespace():
    """transcribe_audio should return clean stripped text."""
    with patch("sebastian.stt._load_config", return_value=STUB_CONFIG), \
         patch("sebastian.stt.WhisperModel") as mock_model_cls:
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "  hello world  "
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_model_cls.return_value = mock_model
        import sebastian.stt as stt_mod
        stt_mod._model = None

        from sebastian.stt import transcribe_audio
        fake_audio = np.zeros(16000, dtype=np.float32)
        result = transcribe_audio(fake_audio)
        assert result == "hello world"

def test_transcribe_concatenates_segments():
    """transcribe_audio should join multiple segments."""
    with patch("sebastian.stt._load_config", return_value=STUB_CONFIG), \
         patch("sebastian.stt.WhisperModel") as mock_model_cls:
        mock_model = MagicMock()
        seg1 = MagicMock(); seg1.text = "hello"
        seg2 = MagicMock(); seg2.text = " world"
        mock_model.transcribe.return_value = ([seg1, seg2], None)
        mock_model_cls.return_value = mock_model
        import sebastian.stt as stt_mod
        stt_mod._model = None

        from sebastian.stt import transcribe_audio
        result = transcribe_audio(np.zeros(16000, dtype=np.float32))
        assert result == "hello world"


def _record(levels):
    """Run record_until_silence on fake mic chunks (100 ms each, given RMS)."""
    import sys, types
    import sebastian.stt as stt
    it = iter(levels)

    class Stream:
        def __init__(self, **_): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n):
            lv = next(it, levels[-1])
            return (np.random.default_rng(0).standard_normal(n) * lv).astype(np.float32).reshape(-1, 1), False

    cfg = {"stt": {"silence_seconds": 1.2, "no_speech_timeout": 6}}
    with patch.dict(sys.modules, {"sounddevice": types.SimpleNamespace(InputStream=Stream)}), \
         patch("sebastian.stt._load_config", return_value=cfg):
        return len(stt.record_until_silence()) / 16000


@pytest.mark.parametrize("before", [[0.003] * 5, [0.02] * 5, [0.0] * 2 + [0.02] * 3, [0.08] * 3 + [0.02] * 3])
def test_stops_soon_after_you_stop_talking(before):
    # quiet room / fan noise / mic starts at zero / echo of "Yes?"
    assert _record(before + [0.2] * 15 + [0.02 if before[-1] >= 0.02 else 0.003] * 400) < 4


def test_gives_up_when_nobody_speaks():
    assert _record([0.02] * 400) < 1
