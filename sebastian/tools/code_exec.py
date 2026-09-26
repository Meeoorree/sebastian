import subprocess
import sys
import tempfile
import os
from sebastian.config import load as _load_config


def run_python(code: str) -> str:
    """Run Python code in a separate process. Returns stdout/stderr.

    Not a sandbox: the code has the owner's full permissions, only a timeout.
    That is why run_python waits for the owner's yes (see sebastian/confirm.py).
    """
    timeout = _load_config()["tools"]["code_timeout"]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        fname = f.name
    try:
        result = subprocess.run(
            [sys.executable, fname],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Code execution timed out after {timeout}s."
    except Exception as e:
        return f"Execution error: {e}"
    finally:
        try:
            os.unlink(fname)
        except OSError:
            pass
