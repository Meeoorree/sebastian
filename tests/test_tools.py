# tests/test_tools.py
import pytest
from unittest.mock import patch, MagicMock

STUB_CONFIG = {
    "tools": {
        "allowed_paths": [],  # overridden per test
        "code_timeout": 2,
    }
}

# --- web_search ---

def test_web_search_returns_formatted_string():
    with patch("sebastian.tools.web_search.DDGS") as mock_ddgs:
        mock_ddgs.return_value.text.return_value = [
            {"title": "Python", "body": "A programming language.", "href": "https://python.org"}
        ]
        from sebastian.tools.web_search import search
        result = search("what is Python")
        assert isinstance(result, str)
        assert "Python" in result

def test_web_search_returns_no_results_message():
    with patch("sebastian.tools.web_search.DDGS") as mock_ddgs:
        mock_ddgs.return_value.text.return_value = []
        from sebastian.tools.web_search import search
        result = search("xyzzy nothing happens")
        assert result == "No results found."

# --- code_exec ---

def test_code_exec_returns_stdout():
    with patch("sebastian.tools.code_exec._load_config", return_value=STUB_CONFIG):
        from sebastian.tools.code_exec import run_python
        result = run_python("print('hello sebastian')")
        assert "hello sebastian" in result

def test_code_exec_returns_stderr_on_error():
    with patch("sebastian.tools.code_exec._load_config", return_value=STUB_CONFIG):
        from sebastian.tools.code_exec import run_python
        result = run_python("raise ValueError('test error')")
        assert "ValueError" in result or "error" in result.lower()

def test_code_exec_times_out():
    with patch("sebastian.tools.code_exec._load_config", return_value=STUB_CONFIG):
        from sebastian.tools.code_exec import run_python
        result = run_python("import time; time.sleep(999)")
        assert "timeout" in result.lower() or "timed out" in result.lower()

# --- file_ops ---

def test_file_write_and_read(tmp_path):
    cfg = {"tools": {"allowed_paths": [str(tmp_path)], "code_timeout": 10}}
    with patch("sebastian.tools.file_ops._load_config", return_value=cfg):
        from sebastian.tools.file_ops import read_file, write_file
        write_file(str(tmp_path / "test.txt"), "hello")
        content = read_file(str(tmp_path / "test.txt"))
        assert content == "hello"

def test_file_read_blocked_outside_allowed(tmp_path):
    cfg = {"tools": {"allowed_paths": [str(tmp_path)], "code_timeout": 10}}
    with patch("sebastian.tools.file_ops._load_config", return_value=cfg):
        from sebastian.tools.file_ops import read_file
        with pytest.raises(PermissionError):
            read_file("C:/Windows/System32/config/SAM")

# --- router ---

def test_router_dispatch_unknown_tool():
    from sebastian.tools.router import dispatch
    result = dispatch("nonexistent_tool", {})
    assert "Unknown tool" in result

def test_router_dispatch_known_tool():
    with patch("sebastian.tools.router.search") as mock_search:
        mock_search.return_value = "Search result"
        from sebastian.tools.router import dispatch
        result = dispatch("web_search", {"query": "test"})
        assert result == "Search result"
