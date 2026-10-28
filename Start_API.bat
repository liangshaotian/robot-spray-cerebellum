@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -m spray_cerebellum
) else (
  python -m spray_cerebellum
)
endlocal
