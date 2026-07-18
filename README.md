# FocusGuard Agent

AI-assisted focus monitor for Windows. It watches the current screen, detects distraction, and uses short English-to-Japanese translation challenges to help the user return to work.

## Quick Start

First-time setup:

```bat
setup_windows.bat
```

Daily stable use:

```bat
start_stable.bat
```

Development mode:

```bat
start_dev.bat
```

Open Electron against the dev servers:

```bat
start_dev.bat electron
```

## Configuration

Create or edit `.env` in the project root:

```env
OPENROUTER_API_KEY=sk-or-your-real-key
```

User settings are stored locally in:

```text
data/prod/settings.json
```

Dev mode uses `data/dev/`; stable packaged mode uses `data/prod/`.

## Build Release

Run:

```powershell
powershell -ExecutionPolicy Bypass -File package_release.ps1
```

Release artifacts are written to:

```text
electron/release/
```

The dated release names use this format:

```text
FocusGuard-Agent-<version>-<YYYY-MM-DD>-win-unpacked/
FocusGuard-Agent-<version>-<YYYY-MM-DD>-win-unpacked.zip
```

Example:

```text
FocusGuard-Agent-1.0.1-2026-07-18-win-unpacked.zip
```

## Notes

- The app captures the display containing the mouse cursor by default.
- Set `AIMONITOR_SCREENSHOT_MODE=full` to capture the full virtual screen.
- The packaged Windows app is distributed as `win-unpacked` because the single-file portable build requires NSIS downloads during packaging.
