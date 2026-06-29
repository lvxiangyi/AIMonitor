# 🛡️ FocusGuard Agent

AI 学习监督助手 — 通过屏幕理解用户行为，在分心时主动干预。

## 快速启动

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

```
OPENAI_API_KEY=sk-your-real-key-here
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
