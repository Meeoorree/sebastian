@echo off
title Sebastian Installer
echo.
echo  ============================================
echo   Sebastian - AI Voice Assistant Installer
echo  ============================================
echo.

:: Check for Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python not found in PATH.
    echo     Checking common install locations...
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        echo     Found Python 3.12
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        echo     Found Python 3.11
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
        set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        echo     Found Python 3.13
    ) else (
        echo [ERROR] Python 3.11+ not found. Install from https://python.org
        pause
        exit /b 1
    )
) else (
    set "PYTHON=python"
)

echo.
echo [1/4] Creating virtual environment...
"%PYTHON%" -m venv .venv
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

echo [2/4] Activating environment...
call .venv\Scripts\activate.bat

echo [3/4] Installing dependencies (this may take a few minutes)...
pip install -r requirements.txt --quiet --retries 10 --timeout 60
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [4/4] Downloading speech models (wake word, Whisper)...
set "HF_HOME=%~dp0model_cache"
python setup_sebastian.py
if %errorlevel% neq 0 (
    echo [ERROR] Model download failed - re-run install.bat.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   Installation complete!
echo  ============================================
echo.
echo  To start Sebastian, run:  start.bat
echo  Then say "Sebastian" and give a command.
echo.
echo  Web UI will open at: http://localhost:7860
echo  Set your key first:  setx DEEPSEEK_API_KEY "your-key"
echo.
pause
