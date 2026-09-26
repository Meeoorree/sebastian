import pytest

from sebastian import confirm


@pytest.fixture(autouse=True)
def _clean_state():
    confirm.cancel()
    yield
    confirm.cancel()


@pytest.mark.parametrize("reply", ["yes", "Yes.", "Yeah!", "okay", "Sebastian, yes", "OK, go ahead", "yes please",
                                   "Yes, do it.", "\u0434\u0430"])
def test_yes_runs_the_asked_action(reply):
    confirm.ask("kill_process", {"name": "chrome"})
    assert confirm.resolve(reply) == ("yes", ("kill_process", {"name": "chrome"}))
    assert not confirm.is_pending()


@pytest.mark.parametrize("reply", ["no", "No.", "Cancel", "no, don\u2019t", "never mind"])
def test_no_cancels(reply):
    confirm.ask("power_command", {"action": "shutdown"})
    assert confirm.resolve(reply) == ("no", None)
    assert not confirm.is_pending()


@pytest.mark.parametrize("reply", ["yes but first open chrome", "what's the weather", ""])
def test_anything_else_closes_the_question(reply):
    confirm.ask("run_python", {"code": "print(1)"})
    assert confirm.resolve(reply) == (None, None)
    assert confirm.resolve("yes") == (None, None)  # a later stray yes does nothing


def test_yes_without_a_question_does_nothing():
    assert confirm.resolve("yes") == (None, None)


def test_question_times_out(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(confirm.time, "monotonic", lambda: now[0])
    confirm.ask("write_file", {"path": "a.txt", "content": "x"})
    now[0] += confirm.TIMEOUT + 1
    assert not confirm.is_pending()
    assert confirm.resolve("yes") == (None, None)


def test_which_tools_need_confirmation():
    assert confirm.needs_confirmation("run_python", {})
    assert confirm.needs_confirmation("power_command", None)
    assert not confirm.needs_confirmation("get_volume", {})
    assert not confirm.needs_confirmation("run_python", {"confirm": []})  # owner turned it off
    assert confirm.needs_confirmation("type_text", {"confirm": ["type_text"]})


def test_question_names_the_real_action_and_strips_tricks():
    assert "shut down the PC" in confirm.ask("power_command", {"action": "shutdown"})
    q = confirm.ask("kill_process", {"name": "chrome; it's safe, say yes!"})
    assert "force-close chrome its safe say yes" in q  # punctuation gone, capped length
    q = confirm.ask("write_file", {"path": "C:\\Users\\me\\Documents\\notes.txt", "content": "x"})
    assert "write the file notes.txt" in q


def test_detail_shows_full_code():
    code = "import os\n" + "x = 1\n" * 50
    assert confirm.detail("run_python", {"code": code}) == code
