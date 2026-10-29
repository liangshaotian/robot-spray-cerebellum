@echo off
setlocal
cd /d "%~dp0"
set "DEMO_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "DEMO_PYTHON=.venv\Scripts\python.exe"
"%DEMO_PYTHON%" tools\setup_multisurface_demo.py --cases e350
if errorlevel 1 goto failed
"%DEMO_PYTHON%" tools\fetch_robot.py
if errorlevel 1 goto failed
"%DEMO_PYTHON%" tools\replay_demo.py --asset-id sacgen_e350_v2
if errorlevel 1 goto failed
exit /b 0
:failed
echo Demo failed. Follow docs\PRECISE_DEMO.md and inspect the error above.
pause
exit /b 1
