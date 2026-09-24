import json
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from sebastian import wake

CFG = {"wake_word": {"name": "Sebastian", "vosk_model": ".", "chunk_size": 1600,
                     "phrases": ["hey sebastian"], "stop_phrases": ["shut up", "stop"]}}


def _run(heard, speaking="", callback=None):
    """Feed recognizer results one per mic read; return (abort mock, callback calls)."""
    started, release = threading.Event(), threading.Event()
    calls = []

    def cb():
        calls.append(1)
        started.set()
        release.wait(2)

    class Rec:
        def __init__(self, *a):
            self.grammar = json.loads(a[2])
            self.i = -1

        def AcceptWaveform(self, _):
            self.i += 1
            if self.i >= len(heard):
                raise KeyboardInterrupt
            if self.i == 1:
                assert started.wait(2)  # first phrase woke us; now we're busy
            return True

        def Result(self):
            return json.dumps({"text": heard[self.i]})

        def Reset(self):
            pass

    mic = SimpleNamespace(read=lambda *a, **k: bytes(3200), is_active=lambda: True,
                          stop_stream=lambda: None, start_stream=lambda: None, close=lambda: None)
    abort = Mock()
    times = iter(range(0, 1000, 10))  # every read is past the cooldowns
    modules = {
        "pyaudio": SimpleNamespace(PyAudio=lambda: SimpleNamespace(open=lambda **_: mic, terminate=lambda: None), paInt16=8),
        "vosk": SimpleNamespace(Model=lambda p: None, KaldiRecognizer=Rec, SetLogLevel=lambda n: None),
        "sebastian.main": SimpleNamespace(abort_all=abort),
        "sebastian.tts": SimpleNamespace(is_speaking=lambda: bool(speaking), current_text=lambda: speaking),
    }
    with patch.dict(sys.modules, modules), patch.object(wake, "_load_config", return_value=CFG), \
         patch.object(wake, "time", SimpleNamespace(time=lambda: next(times), sleep=lambda _: None)):
        try:
            with pytest.raises(KeyboardInterrupt):
                wake.listen_for_wake_word(cb)
        finally:
            release.set()
    return abort, calls


def test_wake_phrase_starts_request_and_stop_phrase_aborts():
    abort, calls = _run(["hey sebastian", "shut up"])
    assert calls == [1]
    abort.assert_called_once()


def test_stop_word_in_own_speech_is_ignored():
    abort, _ = _run(["hey sebastian", "stop"], speaking="I'll stop the timer now.")
    abort.assert_not_called()


def test_wake_phrase_while_busy_does_not_abort_or_restart():
    abort, calls = _run(["hey sebastian", "hey sebastian", "[unk]"])
    assert calls == [1]
    abort.assert_not_called()


def test_matches_whole_words_only():
    assert wake._matches("please stop", ["stop"]) == "stop"
    assert wake._matches("unstoppable", ["stop"]) is None
