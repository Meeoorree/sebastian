import subprocess
import os
import shutil
import webbrowser

_USER = os.environ.get("USERNAME", "User")


def _steam_exe() -> str:
    r"""Resolve steam.exe from the registry, falling back to common install dirs.

    The old hardcoded C:\Program Files (x86)\Steam path is wrong on this box —
    Steam actually lives on E:. Ask Windows instead of guessing.
    """
    import winreg
    for root, subkey in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
    ):
        for value in ("SteamExe", "InstallPath"):
            try:
                with winreg.OpenKey(root, subkey) as k:
                    v = winreg.QueryValueEx(k, value)[0]
            except Exception:
                continue
            exe = v if str(v).lower().endswith(".exe") else os.path.join(str(v), "steam.exe")
            if os.path.exists(exe):
                return exe
    return r"C:\Program Files (x86)\Steam\steam.exe"

APP_MAP = {
    # Browsers
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    # Communication
    "discord": rf"C:\Users\{_USER}\AppData\Local\Discord\Update.exe",
    "telegram": rf"C:\Users\{_USER}\AppData\Roaming\Telegram Desktop\Telegram.exe",
    "slack": rf"C:\Users\{_USER}\AppData\Local\slack\slack.exe",
    "teams": rf"C:\Users\{_USER}\AppData\Local\Microsoft\Teams\current\Teams.exe",
    "zoom": rf"C:\Users\{_USER}\AppData\Roaming\Zoom\bin\Zoom.exe",
    # Dev tools
    "vscode": "code",
    "vs code": "code",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "git bash": rf"C:\Program Files\Git\git-bash.exe",
    # Media
    "spotify": rf"C:\Users\{_USER}\AppData\Roaming\Spotify\Spotify.exe",
    "vlc": r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    # Gaming ("steam" is looked up in the registry when opened, see _program)
    "epic games": r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
    # Productivity
    "notepad": "notepad.exe",
    "notepad++": r"C:\Program Files\Notepad++\notepad++.exe",
    "word": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "excel": r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    "powerpoint": r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    "paint": "mspaint.exe",
    "snipping tool": "SnippingTool.exe",
    # System
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "calculator": "calc.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
}

_FALLBACKS = {
    "chrome": r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "google chrome": r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "edge": r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
}

# Discord needs --processStart flag
_ARGS = {
    "discord": ["--processStart", "Discord.exe"],
}


def _program(key: str) -> str:
    if key == "steam":
        return _steam_exe()  # registry lookup: only on Windows, only when asked
    return APP_MAP.get(key, key)


def _find(program: str) -> str | None:
    """Full path of a program, searched like the command prompt does.
    Popen alone only adds .exe, so "code" (VS Code's code.cmd) failed with WinError 2."""
    return shutil.which(program) or (program if os.path.isfile(program) else None)


def open_app(name: str) -> str:
    """Open an application by friendly name, a program on PATH, or anything Windows can open."""
    key = name.lower().strip()
    program = _program(key)
    for candidate in (program, _FALLBACKS.get(key)):
        path = candidate and _find(candidate)
        if not path:
            continue
        # .cmd/.bat launchers (VS Code) would flash a console window
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if path.lower().endswith((".cmd", ".bat")) else 0
        try:
            subprocess.Popen([path] + _ARGS.get(key, []), creationflags=flags)  # no shell=True
            return f"Opening {name}."
        except OSError:
            continue
    # Not a file we can find: let Windows resolve it (ms-settings:, App Paths like "chrome", Start-menu names)
    target = key if os.path.isabs(program) else program
    try:
        os.startfile(target)  # noqa: S606 - intended shell launch
        return f"Opening {name}."
    except Exception as e:
        return f"Could not open {name}: {e}"


def launch_steam_game(appid, name: str = "") -> str:
    """Start an installed Steam game via the steam:// protocol.

    os.startfile() goes through ShellExecute, so the request is handed to the
    Steam client — it does NOT open a browser. Steam itself is launched first by
    the macro's preceding open_app step, so by the time this runs the client is
    already up and just receives the rungameid request.
    """
    url = f"steam://rungameid/{appid}"
    try:
        os.startfile(url)  # noqa: S606 - intended shell protocol launch
        return f"Starting {name or ('appid ' + str(appid))}."
    except Exception as e:
        return f"Could not start Steam game {appid}: {e}"


def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}."


def kill_process(name: str) -> str:
    """Kill a process by name (e.g. 'spotify', 'chrome')."""
    # Sanitize: only allow alphanumeric, dots, spaces, hyphens
    safe = "".join(c for c in name if c.isalnum() or c in ".-_ ")
    result = subprocess.run(
        ["taskkill", "/IM", f"{safe}.exe", "/F"],
        capture_output=True, text=True,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return f"Killed {name}."
    return f"Could not kill {name}: {output}"
