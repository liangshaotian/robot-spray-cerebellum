@echo off
setlocal
cd /d "%~dp0"
set "DEMO_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "DEMO_PYTHON=.venv\Scripts\python.exe"
"%DEMO_PYTHON%" tools\replay_demo.py --asset-id sacgen_e350_v2 --show-only
if errorlevel 1 pause
