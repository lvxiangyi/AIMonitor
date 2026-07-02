@echo off
setlocal
cd /d %~dp0

if not exist "backend\.venv\Scripts\activate.bat" (
  echo backend\.venv was not found. Run setup_windows.bat first.
  pause
  exit /b 1
)

start "AIMonitor Backend Dev" cmd /k "cd /d %~dp0backend && set AIMONITOR_DATA_ENV=dev&& call .venv\Scripts\activate.bat && uvicorn main:app --reload --host 127.0.0.1 --port 8000"
start "AIMonitor Frontend Dev" cmd /k "cd /d %~dp0frontend && npm run dev"

if /I "%~1"=="electron" (
  start "AIMonitor Electron Dev" cmd /k "cd /d %~dp0electron && set AIMONITOR_DATA_ENV=dev&& set AIMONITOR_ELECTRON_DEV=1&& set AIMONITOR_SKIP_BACKEND=1&& set AIMONITOR_BACKEND_PORT=8000&& npm start"
)

echo Development servers are starting.
echo Frontend: http://127.0.0.1:3000
echo Backend:  http://127.0.0.1:8000
echo To also open Electron in dev mode, run: start_dev.bat electron
