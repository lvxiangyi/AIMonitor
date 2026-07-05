from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import json

from data_paths import LOGS_DIR
from session_manager import session_manager
from schedule_manager import add_schedule, get_schedules, delete_schedule
from auto_scheduler import auto_scheduler
from ai_status_manager import get_ai_status
from report_manager import get_daily_report
from flow_manager import flow_manager
from quiz_generator import generate_quiz, record_wrong_answer, get_wrong_answers
from settings_manager import get_settings_payload, save_settings

app = FastAPI(title="FocusGuard Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    auto_scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    auto_scheduler.stop()

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


class SettingsRequest(BaseModel):
    model: str


class FlowContinueRequest(BaseModel):
    task: str
    duration_minutes: int
    check_interval_seconds: int = 30


class FlowBreakRequest(BaseModel):
    break_minutes: int
    activity: str
    task: str
    duration_minutes: int
    check_interval_seconds: int = 30


class FlowPauseDayRequest(BaseModel):
    activity: str


class FlowResumeRequest(BaseModel):
    break_id: Optional[str] = None
    task: Optional[str] = None
    duration_minutes: Optional[int] = None
    check_interval_seconds: Optional[int] = None
    activity: Optional[str] = None
    break_minutes: Optional[int] = None
    started_at: Optional[str] = None


@app.post("/session/start")
async def start_session(req: StartSessionRequest):
    try:
        session_id = session_manager.start_session(
            task=req.task,
            duration_minutes=req.duration_minutes,
            check_interval_seconds=req.check_interval_seconds,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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


# --- Flow Schedule APIs ---

@app.post("/flow/continue")
async def api_flow_continue(req: FlowContinueRequest):
    try:
        session_id = flow_manager.continue_work(
            task=req.task,
            duration_minutes=req.duration_minutes,
            check_interval_seconds=req.check_interval_seconds,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "started", "session_id": session_id}


@app.post("/flow/break")
async def api_flow_break(req: FlowBreakRequest):
    if req.break_minutes <= 0:
        raise HTTPException(status_code=400, detail="Break minutes must be greater than 0.")
    if not req.activity.strip():
        raise HTTPException(status_code=400, detail="Activity is required.")
    if not req.task.strip():
        raise HTTPException(status_code=400, detail="Task is required.")
    flow_manager.start_break(
        break_minutes=req.break_minutes,
        activity=req.activity.strip(),
        task=req.task.strip(),
        duration_minutes=req.duration_minutes,
        check_interval_seconds=req.check_interval_seconds,
    )
    return {"status": "break_started"}


@app.post("/flow/resume")
async def api_flow_resume(req: FlowResumeRequest):
    payload = req.dict(exclude_none=True) if req.task else None
    try:
        session_id = flow_manager.resume_after_break(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "started", "session_id": session_id}


@app.post("/flow/pause-day")
async def api_flow_pause_day(req: FlowPauseDayRequest):
    activity = req.activity.strip()
    if not activity:
        raise HTTPException(status_code=400, detail="Activity is required.")
    flow_manager.pause_day(activity)
    return {"status": "day_paused"}


# --- Settings APIs ---

@app.get("/settings")
async def api_get_settings():
    return get_settings_payload()


@app.post("/settings")
async def api_save_settings(req: SettingsRequest):
    try:
        settings = save_settings({"model": req.model})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"settings": settings, "status": "saved"}


@app.get("/ai/status")
async def api_ai_status():
    return get_ai_status()


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
    end_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    check_interval_seconds: int = 30


class DeleteScheduleRequest(BaseModel):
    schedule_id: str


@app.get("/schedule/list")
async def api_list_schedules():
    return {"schedules": get_schedules()}


@app.post("/schedule/add")
async def api_add_schedule(req: ScheduleRequest):
    try:
        entry = add_schedule(
            task=req.task,
            date=req.date,
            start_time=req.start_time,
            end_time=req.end_time,
            duration_minutes=req.duration_minutes,
            check_interval_seconds=req.check_interval_seconds,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "added", "schedule": entry}


@app.post("/schedule/delete")
async def api_delete_schedule(req: DeleteScheduleRequest):
    success = delete_schedule(req.schedule_id)
    return {"status": "deleted" if success else "not_found"}


@app.get("/report/daily")
async def api_daily_report(date: Optional[str] = None):
    return get_daily_report(date)


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
