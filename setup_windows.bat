@echo off
setlocal
cd /d %~dp0

if not exist "backend\.venv" (
  cd /d %~dp0backend
  python -m venv .venv
  if errorlevel 1 goto error
) else (
  cd /d %~dp0backend
)

call .venv\Scripts\activate.bat
if errorlevel 1 goto error

python -m pip install --upgrade pip
if errorlevel 1 goto error

pip install -r requirements.txt
if errorlevel 1 goto error

cd /d %~dp0frontend
call npm install
if errorlevel 1 goto error

call npm run build
if errorlevel 1 goto error

cd /d %~dp0electron
call npm install
if errorlevel 1 goto error

echo Setup complete.
echo Run start_stable.bat to start the app.
echo To auto-start on Windows login, create a shortcut to start_stable.bat and place it in shell:startup.
exit /b 0

:error
echo Setup failed. See the error above.
pause
exit /b 1
