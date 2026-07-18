import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from data_paths import DATASET_DB, DATASET_DIR, DATASET_EXPORT_DIR, DATASET_SCREENSHOT_DIR
from screenshot import take_screenshot


ALLOWED_LABELS = {"on_task", "off_task", "ambiguous", "unlabeled"}
PROMPT_VERSION = "v1"
DEFAULT_TAGS = ["guardian mode"]


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _connect():
    DATASET_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATASET_DB)
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def _init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS samples (
            id TEXT PRIMARY KEY,
            screenshot_path TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            session_id TEXT,
            task TEXT NOT NULL,

            activity TEXT,
            distraction_label TEXT NOT NULL DEFAULT 'unlabeled',
            label_notes TEXT,
            tags TEXT NOT NULL DEFAULT '["guardian mode"]',

            source TEXT NOT NULL DEFAULT 'hotkey',
            reviewed INTEGER NOT NULL DEFAULT 0,

            ai_on_task INTEGER,
            ai_confidence REAL,
            ai_activity TEXT,
            ai_reason TEXT,
            ai_model TEXT,
            prompt_version TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(samples)").fetchall()}
    if "tags" not in columns:
        conn.execute("""ALTER TABLE samples ADD COLUMN tags TEXT NOT NULL DEFAULT '["guardian mode"]'""")
    conn.commit()


def _row_to_dict(row) -> Optional[dict]:
    if not row:
        return None
    data = dict(row)
    data["reviewed"] = bool(data.get("reviewed"))
    if data.get("ai_on_task") is not None:
        data["ai_on_task"] = bool(data["ai_on_task"])
    data["tags"] = _normalize_tags(data.get("tags"), default_to_guardian=data.get("tags") in (None, ""))
    data["screenshot_url"] = f"/dataset/samples/{data['id']}/image"
    return data


def _normalize_tags(value, default_to_guardian: bool = False) -> list:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                raw_items = parsed
            else:
                raw_items = value.replace("，", "\n").replace(",", "\n").splitlines()
        except Exception:
            raw_items = value.replace("，", "\n").replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    normalized = []
    seen = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)

    if not normalized and default_to_guardian:
        return DEFAULT_TAGS.copy()
    return normalized


def _validate_label(label: str) -> str:
    value = (label or "unlabeled").strip()
    if value not in ALLOWED_LABELS:
        raise ValueError(f"Unsupported distraction_label: {value}")
    return value


def _relative_screenshot_path(sample_id: str, captured_at: str) -> str:
    day = datetime.fromisoformat(captured_at).date().isoformat()
    return str(Path("screenshots") / day / f"{sample_id}.jpg").replace("\\", "/")


def _absolute_screenshot_path(relative_path: str) -> Path:
    return DATASET_DIR / relative_path


def create_sample(
    task: str,
    label: str = "unlabeled",
    session_id: Optional[str] = None,
    activity: Optional[str] = None,
    label_notes: Optional[str] = None,
    tags: Optional[list] = None,
    source: str = "hotkey",
    ai_prediction: Optional[dict] = None,
) -> dict:
    sample_id = str(uuid.uuid4())
    captured_at = _now()
    relative_path = _relative_screenshot_path(sample_id, captured_at)
    output_path = _absolute_screenshot_path(relative_path)

    if output_path.exists():
        raise FileExistsError(f"Screenshot path already exists: {output_path}")

    take_screenshot(output_path=str(output_path))

    now = _now()
    ai_prediction = ai_prediction or {}
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO samples (
                id, screenshot_path, captured_at, session_id, task,
                activity, distraction_label, label_notes, tags, source, reviewed,
                ai_on_task, ai_confidence, ai_activity, ai_reason, ai_model, prompt_version,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                relative_path,
                captured_at,
                session_id,
                (task or "unspecified").strip() or "unspecified",
                activity,
                _validate_label(label),
                label_notes,
                json.dumps(_normalize_tags(DEFAULT_TAGS if tags is None else tags, default_to_guardian=True), ensure_ascii=False),
                source or "hotkey",
                0,
                None if ai_prediction.get("on_task") is None else int(bool(ai_prediction.get("on_task"))),
                ai_prediction.get("confidence"),
                ai_prediction.get("current_activity") or ai_prediction.get("activity"),
                ai_prediction.get("reason"),
                ai_prediction.get("model"),
                ai_prediction.get("prompt_version") or PROMPT_VERSION,
                now,
                now,
            ),
        )
        conn.commit()

    return get_sample(sample_id)


def get_sample(sample_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
    return _row_to_dict(row)


def list_samples(label: Optional[str] = None, reviewed: Optional[bool] = None, limit: int = 100, offset: int = 0) -> list:
    clauses = []
    params = []
    if label:
        clauses.append("distraction_label = ?")
        params.append(_validate_label(label))
    if reviewed is not None:
        clauses.append("reviewed = ?")
        params.append(1 if reviewed else 0)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([max(1, min(int(limit or 100), 500)), max(0, int(offset or 0))])
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM samples {where} ORDER BY captured_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def update_sample(sample_id: str, **updates) -> Optional[dict]:
    allowed = {
        "activity",
        "distraction_label",
        "label_notes",
        "tags",
        "reviewed",
        "ai_on_task",
        "ai_confidence",
        "ai_activity",
        "ai_reason",
        "ai_model",
        "prompt_version",
    }
    fields = []
    params = []
    for key, value in updates.items():
        if key not in allowed or value is None:
            continue
        if key == "distraction_label":
            value = _validate_label(value)
        if key == "tags":
            value = json.dumps(_normalize_tags(value), ensure_ascii=False)
        if key in {"reviewed", "ai_on_task"}:
            value = int(bool(value))
        fields.append(f"{key} = ?")
        params.append(value)

    if not fields:
        return get_sample(sample_id)

    fields.append("updated_at = ?")
    params.append(_now())
    params.append(sample_id)
    with _connect() as conn:
        conn.execute(f"UPDATE samples SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    return get_sample(sample_id)


def delete_sample(sample_id: str, delete_image: bool = True) -> bool:
    sample = get_sample(sample_id)
    if not sample:
        return False
    with _connect() as conn:
        conn.execute("DELETE FROM samples WHERE id = ?", (sample_id,))
        conn.commit()
    if delete_image:
        try:
            image_path = _absolute_screenshot_path(sample["screenshot_path"]).resolve()
            dataset_root = DATASET_DIR.resolve()
            if dataset_root in image_path.parents and image_path.exists():
                image_path.unlink()
        except Exception as e:
            print(f"[dataset] Could not delete image for {sample_id}: {e}")
    return True


def export_jsonl(output_path: Optional[str] = None) -> dict:
    output = Path(output_path) if output_path else DATASET_EXPORT_DIR / "dataset.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM samples ORDER BY captured_at DESC").fetchall()
    samples = [_row_to_dict(row) for row in rows]
    with open(output, "w", encoding="utf-8") as f:
        for sample in samples:
            item = {
                "id": sample["id"],
                "image_path": sample["screenshot_path"],
                "captured_at": sample["captured_at"],
                "task": sample["task"],
                "tags": sample.get("tags") or DEFAULT_TAGS,
                "activity": sample.get("activity") or "",
                "ground_truth": sample["distraction_label"],
                "notes": sample.get("label_notes") or "",
                "reviewed": bool(sample.get("reviewed")),
                "ai_prediction": {
                    "on_task": sample.get("ai_on_task"),
                    "confidence": sample.get("ai_confidence"),
                    "activity": sample.get("ai_activity"),
                    "reason": sample.get("ai_reason"),
                    "model": sample.get("ai_model"),
                    "prompt_version": sample.get("prompt_version"),
                },
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return {"path": str(output), "count": len(samples)}


def get_screenshot_file(sample_id: str) -> Optional[Path]:
    sample = get_sample(sample_id)
    if not sample:
        return None
    path = _absolute_screenshot_path(sample["screenshot_path"]).resolve()
    try:
        if DATASET_DIR.resolve() not in path.parents:
            return None
    except Exception:
        return None
    return path if path.exists() else None
