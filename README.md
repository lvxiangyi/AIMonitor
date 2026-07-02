# 🛡️ FocusGuard Agent

AI 学习监督助手 — 通过屏幕理解用户行为，在分心时主动干预。

## Run as a Windows desktop app

This is the recommended workflow for daily personal use on Windows.

### First-time setup

Double-click:

```bat
setup_windows.bat
```

This creates `backend/.venv`, installs backend dependencies, installs frontend dependencies, builds `frontend/dist`, and installs Electron dependencies.

### Daily stable use

Double-click:

```bat
start_stable.bat
```

Stable mode opens the Electron desktop window, starts the FastAPI backend automatically with `backend/.venv/Scripts/python.exe`, and loads the already-built `frontend/dist/index.html`. It does not require or start the Vite frontend dev server.

### Rebuild frontend after frontend changes

Only when you change frontend code, run:

```bat
build_frontend.bat
```

Then use `start_stable.bat` again.

### Development mode

For active development, run:

```bat
start_dev.bat
```

This opens the reload backend on `127.0.0.1:8000` and the Vite frontend dev server on `127.0.0.1:3000` in separate terminals.

To also open Electron against those dev servers:

```bat
start_dev.bat electron
```

Use `start_stable.bat` for daily planning/focus monitoring. Use `start_dev.bat` only when developing.

### Windows auto-start

1. Press Win + R
2. Type `shell:startup`
3. Create a shortcut to `start_stable.bat`
4. Move the shortcut into that folder

### Data safety

Stable mode uses `data/prod/` for logs, schedules, quiz history, and screenshots. Dev mode uses `data/dev/`. Avoid directly modifying stable user data during risky development, and back up local data before database schema or data format changes.

### Multi-monitor screenshots

By default, FocusGuard captures only the display that currently contains the mouse cursor. This avoids sending both monitors to the vision model when a second screen has unrelated content.

To temporarily return to full virtual-screen capture, start the backend/Electron with:

```bat
set AIMONITOR_SCREENSHOT_MODE=full
```

### AI model settings

The default model is `google/gemini-2.5-flash-lite`. You can change the model from the Settings tab in the desktop app. The selected model is saved in:

```text
data/prod/settings.json
```

Current built-in options:

- `google/gemini-2.5-flash-lite`
- `openai/gpt-4o`
- `openai/gpt-4o-mini`

## 快速启动（开发）

### 1. 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:3000

### 3. 配置 API Key（可选）

编辑根目录 `.env` 文件：

```env
OPENROUTER_API_KEY=sk-or-your-real-key-here
```

如果不配置，系统自动使用 mock 模式（随机返回专注/分心结果，方便调试）。

## 使用方式

1. 输入学习目标（例如：学习数学）
2. 设置时长和检查间隔
3. 点击"开始监督"
4. Agent 会定期截图并判断你是否在执行任务
5. 连续 2 次分心会弹出全屏提醒

## 技术栈

- **后端**: Python FastAPI + mss(截图) + OpenAI GPT-4o Vision
- **前端**: React + Vite
