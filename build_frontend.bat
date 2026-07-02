@echo off
setlocal
cd /d %~dp0frontend

if not exist node_modules (
  call npm install
  if errorlevel 1 goto error
)

call npm run build
if errorlevel 1 goto error

echo Frontend build complete.
exit /b 0

:error
echo Frontend build failed.
pause
exit /b 1
