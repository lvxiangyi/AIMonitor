from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import json
import os

from data_paths import LOGS_DIR
from session_manager import session_manager
from schedule_manager import add_schedule, get_schedules, delete_schedule
from auto_scheduler import auto_scheduler
from guardian_manager import guardian_manager
from ai_status_manager import get_ai_status
from report_manager import get_daily_report, save_daily_notes
from flow_manager import flow_manager
from dataset_store import (
    ALLOWED_LABELS,
    create_sample,
    delete_sample,
    export_jsonl,
    get_sample,
    get_screenshot_file,
    list_samples,
    update_sample,
)
from quiz_generator import (
    generate_quiz,
    generate_translation_challenge,
    grade_translation_answer,
    record_wrong_answer,
    get_wrong_answers,
)
from settings_manager import (
    get_default_check_interval_seconds,
    get_default_strict_mode,
    get_default_trigger_threshold,
    get_settings_payload,
    get_strict_status,
    save_settings,
)

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
    guardian_manager.start()
    asyncio.create_task(_replay_pending_flow_prompt())


async def _replay_pending_flow_prompt():
    """Show a saved post-session prompt if the previous attempt was missed."""
    await asyncio.sleep(1.0)
    from flow_prompt_store import load_pending_flow
    from blocker_window import blocker

    pending = load_pending_flow()
    if pending:
        blocker.show_flow_prompt(pending)


@app.on_event("shutdown")
async def shutdown_event():
    auto_scheduler.stop()
    guardian_manager.stop()

# --- Session APIs ---

class StartSessionRequest(BaseModel):
    task: str
    duration_minutes: int = 10
    check_interval_seconds: Optional[int] = None
    trigger_threshold: Optional[int] = None
    tags: List[str] = []
    strict_mode: Optional[bool] = None


class StopSessionRequest(BaseModel):
    session_id: Optional[str] = None
    reason: Optional[str] = None
    stop_minutes: Optional[int] = None
    tags: List[str] = []


class AcknowledgeRequest(BaseModel):
    session_id: Optional[str] = None


class DisputeRequest(BaseModel):
    session_id: Optional[str] = None
    reason: str


class SettingsRequest(BaseModel):
    model: Optional[str] = None
    strict_mode_enabled: Optional[bool] = None
    strict_locked_until: Optional[str] = None
    supervision_level: Optional[str] = None
    nudge_prompt: Optional[str] = None
    default_check_interval_seconds: Optional[int] = None
    trigger_threshold: Optional[int] = None
    whitelist_behaviors: Optional[List[str]] = None
    guardian_mode_enabled: Optional[bool] = None
    guardian_check_interval_seconds: Optional[int] = None
    dataset_tag_options: Optional[List[str]] = None
    dataset_retention_days: Optional[int] = None


class FlowContinueRequest(BaseModel):
    task: str
    duration_minutes: int
    check_interval_seconds: Optional[int] = None
    trigger_threshold: Optional[int] = None
    tags: List[str] = []
    strict_mode: Optional[bool] = None


class FlowBreakRequest(BaseModel):
    break_minutes: int
    activity: str
    task: str
    duration_minutes: int
    check_interval_seconds: Optional[int] = None
    trigger_threshold: Optional[int] = None
    tags: List[str] = []
    strict_mode: Optional[bool] = None


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
    tags: Optional[List[str]] = None
    strict_mode: Optional[bool] = None
    trigger_threshold: Optional[int] = None


class RecoveryWorkRequest(BaseModel):
    minimum_next_step: str


class RecoveryBreakRequest(BaseModel):
    break_minutes: int
    minimum_next_step: str


class DatasetCaptureRequest(BaseModel):
    label: str = "unlabeled"
    tags: Optional[List[str]] = None


class DatasetUpdateRequest(BaseModel):
    activity: Optional[str] = None
    distraction_label: Optional[str] = None
    label_notes: Optional[str] = None
    tags: Optional[List[str]] = None
    reviewed: Optional[bool] = None
    ai_on_task: Optional[bool] = None
    ai_confidence: Optional[float] = None
    ai_activity: Optional[str] = None
    ai_reason: Optional[str] = None
    ai_model: Optional[str] = None
    prompt_version: Optional[str] = None


@app.post("/session/start")
async def start_session(req: StartSessionRequest):
    try:
        flow_manager.cancel_pending_break()
        flow_manager.cancel_pending_stop()
        session_id = session_manager.start_session(
            task=req.task,
            duration_minutes=req.duration_minutes,
            check_interval_seconds=(
                req.check_interval_seconds
                if req.check_interval_seconds is not None
                else get_default_check_interval_seconds()
            ),
            tags=req.tags,
            strict_mode=get_default_strict_mode() if req.strict_mode is None else req.strict_mode,
            trigger_threshold=req.trigger_threshold if req.trigger_threshold is not None else get_default_trigger_threshold(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"session_id": session_id, "status": "started"}


@app.post("/session/stop")
async def stop_session(req: StopSessionRequest):
    if session_manager.active and session_manager.strict_mode:
        raise HTTPException(status_code=403, detail="当前任务开启了强制答题，不能停止。")
    reason = (req.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="请输入停止原因。")
    if not req.stop_minutes or req.stop_minutes <= 0:
        raise HTTPException(status_code=400, detail="请输入需要停止多久。")
    tags = req.tags or session_manager.tags
    session_manager.stop_session(stop_reason=reason)
    flow_manager.start_stop_pause(reason=reason, stop_minutes=req.stop_minutes, tags=tags)
    return {"status": "stopped"}


@app.get("/session/status")
async def get_status():
    status = session_manager.get_status()
    status["flow_status"] = flow_manager.get_status()
    status["guardian_status"] = guardian_manager.get_status()
    status["strict_status"] = {
        **get_strict_status(),
        "session_locked": bool(session_manager.active and session_manager.strict_mode),
    }
    return status


@app.post("/session/acknowledge")
async def acknowledge_block(req: AcknowledgeRequest):
    session_manager.acknowledge_block()
    return {"status": "acknowledged"}


@app.post("/session/dispute")
async def dispute_judgement(req: DisputeRequest):
    result = session_manager.dispute(req.reason)
    return result


@app.post("/session/recovery/work")
async def recovery_work(req: RecoveryWorkRequest):
    try:
        session_manager.choose_recovery_work(req.minimum_next_step)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "work_selected"}


@app.post("/session/recovery/break")
async def recovery_break(req: RecoveryBreakRequest):
    if req.break_minutes <= 0:
        raise HTTPException(status_code=400, detail="休息时长需要是正整数。")
    try:
        payload = session_manager.choose_recovery_break(req.break_minutes, req.minimum_next_step)
        flow_manager.start_break(
            break_minutes=req.break_minutes,
            activity=f"恢复休息：{req.minimum_next_step.strip()}",
            task=payload["task"],
            duration_minutes=payload["duration_minutes"],
            check_interval_seconds=payload["check_interval_seconds"],
            trigger_threshold=payload["trigger_threshold"],
            tags=payload["tags"],
            strict_mode=payload["strict_mode"],
            minimum_next_step=payload["minimum_next_step"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "break_started"}


@app.post("/guardian/recovery/work")
async def guardian_recovery_work(req: RecoveryWorkRequest):
    try:
        guardian_manager.return_to_work(req.minimum_next_step)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "work_selected"}


@app.post("/guardian/recovery/break")
async def guardian_recovery_break(req: RecoveryBreakRequest):
    if req.break_minutes <= 0:
        raise HTTPException(status_code=400, detail="休息时长需要是正整数。")
    try:
        payload = guardian_manager.start_break(req.break_minutes, req.minimum_next_step)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "break_started", "break": payload}


# --- Flow Schedule APIs ---

@app.post("/flow/continue")
async def api_flow_continue(req: FlowContinueRequest):
    try:
        session_id = flow_manager.continue_work(
            task=req.task,
            duration_minutes=req.duration_minutes,
            check_interval_seconds=(
                req.check_interval_seconds
                if req.check_interval_seconds is not None
                else get_default_check_interval_seconds()
            ),
            tags=req.tags,
            strict_mode=req.strict_mode,
            trigger_threshold=req.trigger_threshold if req.trigger_threshold is not None else get_default_trigger_threshold(),
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
        check_interval_seconds=(
            req.check_interval_seconds
            if req.check_interval_seconds is not None
            else get_default_check_interval_seconds()
        ),
        trigger_threshold=req.trigger_threshold if req.trigger_threshold is not None else get_default_trigger_threshold(),
        tags=req.tags,
        strict_mode=req.strict_mode,
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
    if flow_manager.pending_resume and flow_manager.pending_resume.get("strict_mode"):
        raise HTTPException(status_code=403, detail="强制答题锁定中，不能跳过休息后的下一轮。")
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
        update = req.dict(exclude_none=True)
        settings = save_settings(update)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"settings": settings, "status": "saved"}


@app.get("/ai/status")
async def api_ai_status():
    return get_ai_status()


@app.get("/guardian/latest-screenshot")
async def api_guardian_latest_screenshot():
    screenshot_path = guardian_manager.latest_screenshot_path
    if not screenshot_path:
        raise HTTPException(status_code=404, detail="No Guardian screenshot yet.")
    if not os.path.exists(screenshot_path):
        raise HTTPException(status_code=404, detail="Guardian screenshot not found.")
    return FileResponse(screenshot_path, media_type="image/jpeg")


# --- Dataset APIs ---

@app.post("/dataset/capture")
async def api_dataset_capture(req: DatasetCaptureRequest):
    label = req.label or "unlabeled"
    if label not in ALLOWED_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported label.")
    task = session_manager.task if session_manager.active and session_manager.task else "unspecified"
    session_id = session_manager.session_id if session_manager.active else None
    try:
        sample = create_sample(task=task, label=label, session_id=session_id, tags=req.tags, source="hotkey")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Capture failed: {e}")
    return {"status": "captured", "sample": sample}


@app.get("/dataset/samples")
async def api_dataset_samples(
    label: Optional[str] = None,
    reviewed: Optional[bool] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    if label and label not in ALLOWED_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported label.")
    return {"samples": list_samples(label=label, reviewed=reviewed, limit=limit, offset=offset)}


@app.get("/dataset/samples/{sample_id}")
async def api_dataset_sample(sample_id: str):
    sample = get_sample(sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found.")
    return sample


@app.get("/dataset/samples/{sample_id}/image")
async def api_dataset_sample_image(sample_id: str):
    image = get_screenshot_file(sample_id)
    if not image:
        raise HTTPException(status_code=404, detail="Screenshot not found.")
    return FileResponse(str(image), media_type="image/jpeg")


@app.patch("/dataset/samples/{sample_id}")
async def api_dataset_update(sample_id: str, req: DatasetUpdateRequest):
    updates = req.dict(exclude_unset=True)
    if updates.get("distraction_label") and updates["distraction_label"] not in ALLOWED_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported label.")
    sample = update_sample(sample_id, **updates)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found.")
    return sample


@app.delete("/dataset/samples/{sample_id}")
async def api_dataset_delete(sample_id: str, delete_image: bool = True):
    if not delete_sample(sample_id, delete_image=delete_image):
        raise HTTPException(status_code=404, detail="Sample not found.")
    return {"status": "deleted"}


@app.post("/dataset/export")
async def api_dataset_export():
    return {"status": "exported", **export_jsonl()}


@app.post("/dataset/open-folder")
async def api_dataset_open_folder(sample_id: Optional[str] = None):
    from data_paths import DATASET_DIR

    target = DATASET_DIR
    if sample_id:
        image = get_screenshot_file(sample_id)
        if image:
            target = image.parent
    try:
        if os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            raise RuntimeError("Opening folders is only implemented for Windows in this build.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not open folder: {e}")
    return {"status": "opened", "path": str(target)}


# --- Quiz APIs ---

class QuizAnswerRequest(BaseModel):
    question: str
    user_answer: str
    correct_answer: str
    task: str


class TranslationGradeRequest(BaseModel):
    challenge_id: str
    source_text: str
    user_answer: str


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


@app.get("/strict/translation")
async def api_translation_challenge():
    return generate_translation_challenge()


@app.post("/strict/translation/grade")
async def api_translation_grade(req: TranslationGradeRequest):
    if not req.user_answer.strip():
        raise HTTPException(status_code=400, detail="请输入日语翻译。")
    return grade_translation_answer(req.source_text, req.user_answer)


# --- Schedule APIs ---

class ScheduleRequest(BaseModel):
    task: str
    date: str
    start_time: str
    end_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    check_interval_seconds: Optional[int] = None
    trigger_threshold: Optional[int] = None
    tags: List[str] = []
    strict_mode: Optional[bool] = None


class DeleteScheduleRequest(BaseModel):
    schedule_id: str


class DailyNotesRequest(BaseModel):
    date: Optional[str] = None
    today_summary: str = ""
    tomorrow_plan: str = ""


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
            check_interval_seconds=(
                req.check_interval_seconds
                if req.check_interval_seconds is not None
                else get_default_check_interval_seconds()
            ),
            trigger_threshold=req.trigger_threshold if req.trigger_threshold is not None else get_default_trigger_threshold(),
            tags=req.tags,
            strict_mode=get_default_strict_mode() if req.strict_mode is None else req.strict_mode,
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


@app.post("/report/daily-notes")
async def api_save_daily_notes(req: DailyNotesRequest):
    return save_daily_notes(req.date, req.today_summary, req.tomorrow_plan)


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
    from settings_manager import get_nudge_prompt
    task = session_manager.task or "数学"
    if not blocker.is_showing:
        blocker.show(
            task=task,
            activity="テストモード",
            reason="手動テスト",
            strict_mode=bool(session_manager.strict_mode),
            nudge_message=get_nudge_prompt(),
        )
    session_manager.should_block = True
    return {"status": "triggered"}
