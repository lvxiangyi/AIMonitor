from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import json
from pathlib import Path

from session_manager import session_manager
from schedule_manager import add_schedule, get_schedules, delete_schedule
from quiz_generator import generate_quiz, record_wrong_answer, get_wrong_answers

app = FastAPI(title="FocusGuard Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOGS_DIR = Path(__file__).parent.parent / "logs"


# --- Session APIs ---

class StartSessionRequest(BaseModel):
    task: str
    duration_minutes: int = 10
    check_interval_seconds: int = 30


class StopSessionRequest(BaseModel):
    session_id: Optional[str] = None


class AcknowledgeRequest(BaseModel):
    session_id: Optional[str] = None


class DisputeRequest(BaseModel):
    session_id: Optional[str] = None
    reason: str


@app.post("/session/start")
async def start_session(req: StartSessionRequest):
    session_id = session_manager.start_session(
        task=req.task,
        duration_minutes=req.duration_minutes,
        check_interval_seconds=req.check_interval_seconds,
    )
    return {"session_id": session_id, "status": "started"}


@app.post("/session/stop")
async def stop_session(req: StopSessionRequest):
    session_manager.stop_session()
    return {"status": "stopped"}


@app.get("/session/status")
async def get_status():
    return session_manager.get_status()


@app.post("/session/acknowledge")
async def acknowledge_block(req: AcknowledgeRequest):
    session_manager.acknowledge_block()
    return {"status": "acknowledged"}


@app.post("/session/dispute")
async def dispute_judgement(req: DisputeRequest):
    result = session_manager.dispute(req.reason)
    return result


# --- Quiz APIs ---

class QuizAnswerRequest(BaseModel):
    question: str
    user_answer: str
    correct_answer: str
    task: str


@app.get("/quiz/generate")
async def api_generate_quiz(task: str = ""):
    """Generate a quiz question for the given task."""
    t = task or (session_manager.task if session_manager.task else "general study")
    quiz = generate_quiz(t)
    return quiz


@app.post("/quiz/wrong")
async def api_record_wrong(req: QuizAnswerRequest):
    """Record a wrong answer."""
    record_wrong_answer(req.question, req.user_answer, req.correct_answer, req.task)
    return {"status": "recorded"}


@app.get("/quiz/wrong-answers")
async def api_get_wrong_answers():
    """Get all wrong answers for review."""
    return {"wrong_answers": get_wrong_answers()}


# --- Schedule APIs ---

class ScheduleRequest(BaseModel):
    task: str
    date: str
    start_time: str
    duration_minutes: int
    check_interval_seconds: int = 30


class DeleteScheduleRequest(BaseModel):
    schedule_id: str


@app.get("/schedule/list")
async def api_list_schedules():
    return {"schedules": get_schedules()}


@app.post("/schedule/add")
async def api_add_schedule(req: ScheduleRequest):
    entry = add_schedule(
        task=req.task,
        date=req.date,
        start_time=req.start_time,
        duration_minutes=req.duration_minutes,
        check_interval_seconds=req.check_interval_seconds,
    )
    return {"status": "added", "schedule": entry}


@app.post("/schedule/delete")
async def api_delete_schedule(req: DeleteScheduleRequest):
    success = delete_schedule(req.schedule_id)
    return {"status": "deleted" if success else "not_found"}


# --- Analytics / Visualization APIs ---

@app.get("/analytics/summary")
async def api_analytics_summary():
    """Get analytics summary from session logs."""
    log_file = LOGS_DIR / "session_logs.jsonl"
    if not log_file.exists():
        return {"total_checks": 0, "focused_checks": 0, "distracted_checks": 0, "sessions": []}

    logs = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    logs.append(json.loads(line))
                except Exception:
                    pass

    total = len(logs)
    focused = sum(1 for l in logs if l.get("on_task", False))
    distracted = total - focused

    # Group by session
    sessions = {}
    for log in logs:
        sid = log.get("session_id", "unknown")
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "task": log.get("task", ""),
                "total_checks": 0,
                "focused_checks": 0,
                "distracted_checks": 0,
                "start_time": log.get("timestamp", ""),
                "end_time": log.get("timestamp", ""),
                "activities": [],
            }
        sessions[sid]["total_checks"] += 1
        if log.get("on_task", False):
            sessions[sid]["focused_checks"] += 1
        else:
            sessions[sid]["distracted_checks"] += 1
        sessions[sid]["end_time"] = log.get("timestamp", "")
        sessions[sid]["activities"].append({
            "timestamp": log.get("timestamp", ""),
            "on_task": log.get("on_task", False),
            "activity": log.get("current_activity", ""),
            "confidence": log.get("confidence", 0),
        })

    # Top distractions
    distraction_activities = [l.get("current_activity", "") for l in logs if not l.get("on_task", False)]
    distraction_counts = {}
    for a in distraction_activities:
        distraction_counts[a] = distraction_counts.get(a, 0) + 1
    top_distractions = sorted(distraction_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "total_checks": total,
        "focused_checks": focused,
        "distracted_checks": distracted,
        "focus_rate": round(focused / total * 100, 1) if total > 0 else 0,
        "sessions": list(sessions.values()),
        "top_distractions": [{"activity": a, "count": c} for a, c in top_distractions],
    }


@app.get("/")
async def root():
    return {"message": "FocusGuard Agent API is running."}


@app.post("/session/test-block")
async def test_block():
    """Trigger blocker window for testing purposes."""
    from blocker_window import blocker
    task = session_manager.task or "数学"
    if not blocker.is_showing:
        blocker.show(task=task, activity="テストモード", reason="手動テスト")
    session_manager.should_block = True
    return {"status": "triggered"}
