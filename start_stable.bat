@echo off
setlocal
cd /d %~dp0

set "AIMONITOR_DATA_ENV=prod"

if not exist "frontend\dist\index.html" (
  echo Production frontend build not found.
  echo Run build_frontend.bat or setup_windows.bat first.
  pause
  exit /b 1
)

cd electron
call npm start
if errorlevel 1 pause
