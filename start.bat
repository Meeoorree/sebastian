@echo off
title Sebastian
cd /d "%~dp0"
set "HF_HOME=%~dp0model_cache"
set "PYTHONUTF8=1"
call .venv\Scripts\activate.bat
python -m sebastian.main
pause
