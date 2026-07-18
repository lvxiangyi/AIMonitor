import json
from datetime import datetime
from typing import Dict, List

from data_paths import DATA_DIR


SETTINGS_FILE = DATA_DIR / "settings.json"

MODEL_OPTIONS: List[Dict[str, str]] = [
    {
        "id": "google/gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash-Lite",
        "description": "Fast, low-cost multimodal model for daily monitoring.",
    },
    {
        "id": "openai/gpt-4o",
        "label": "GPT-4o",
        "description": "Stronger vision model, usually slower and more expensive.",
    },
    {
        "id": "openai/gpt-4o-mini",
        "label": "GPT-4o mini",
        "description": "Lower-cost OpenAI model for quiz/dispute text tasks.",
    },
]

SUPERVISION_LEVEL_OPTIONS: List[Dict[str, str]] = [
    {
        "id": "task_related",
        "label": "必须和任务强相关",
        "description": "Session mode: only clearly task-related work is accepted. User-defined whitelist behaviors are accepted unless they are hard-blocked content.",
    },
    {
        "id": "not_entertainment",
        "label": "不是明显娱乐即可",
        "description": "Session mode: general productivity, learning, reading, writing, and research are accepted. User-defined whitelist behaviors are accepted unless they are hard-blocked content.",
    },
]

DEFAULT_NUDGE_PROMPT = (
    "先和冲动保持一点距离：你不是这个念头本身，只是在看见一个念头。"
    "请做一个最小下一步，或者明确休息多久后回来。"
)

DEFAULT_SETTINGS = {
    "model": "google/gemini-2.5-flash-lite",
    "strict_mode_enabled": True,
    "strict_locked_until": None,
    "supervision_level": "task_related",
    "nudge_prompt": DEFAULT_NUDGE_PROMPT,
    "default_check_interval_seconds": 300,
    "trigger_threshold": 1,
    "whitelist_behaviors": ["听音乐"],
    "guardian_mode_enabled": True,
    "guardian_check_interval_seconds": 300,
    "dataset_retention_days": None,
}


def _valid_model_ids() -> set:
    return {model["id"] for model in MODEL_OPTIONS}


def _valid_supervision_level_ids() -> set:
    return {level["id"] for level in SUPERVISION_LEVEL_OPTIONS}


def load_settings() -> dict:
    settings = DEFAULT_SETTINGS.copy()

    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                settings.update(saved)
        except Exception as e:
            print(f"[settings] Could not read settings, using defaults: {e}")

    if settings.get("model") not in _valid_model_ids():
        settings["model"] = DEFAULT_SETTINGS["model"]

    if settings.get("supervision_level") not in _valid_supervision_level_ids():
        settings["supervision_level"] = DEFAULT_SETTINGS["supervision_level"]

    if not isinstance(settings.get("nudge_prompt"), str) or not settings.get("nudge_prompt").strip():
        settings["nudge_prompt"] = DEFAULT_SETTINGS["nudge_prompt"]

    try:
        settings["default_check_interval_seconds"] = max(5, int(settings.get("default_check_interval_seconds", 300)))
    except Exception:
        settings["default_check_interval_seconds"] = DEFAULT_SETTINGS["default_check_interval_seconds"]

    try:
        settings["trigger_threshold"] = max(1, int(settings.get("trigger_threshold", 1)))
    except Exception:
        settings["trigger_threshold"] = DEFAULT_SETTINGS["trigger_threshold"]

    settings["whitelist_behaviors"] = _normalize_string_list(settings.get("whitelist_behaviors", []))
    if not settings["whitelist_behaviors"]:
        settings["whitelist_behaviors"] = DEFAULT_SETTINGS["whitelist_behaviors"].copy()

    settings["guardian_mode_enabled"] = bool(settings.get("guardian_mode_enabled", True))
    try:
        settings["guardian_check_interval_seconds"] = max(
            30, int(settings.get("guardian_check_interval_seconds", 300))
        )
    except Exception:
        settings["guardian_check_interval_seconds"] = DEFAULT_SETTINGS["guardian_check_interval_seconds"]

    retention = settings.get("dataset_retention_days")
    if retention in ("", 0):
        retention = None
    if retention is not None:
        try:
            retention = max(1, int(retention))
        except Exception:
            retention = None
    settings["dataset_retention_days"] = retention

    return settings


def save_settings(settings_update: dict) -> dict:
    settings = load_settings()

    if "model" in settings_update:
        model = settings_update["model"]
        if model not in _valid_model_ids():
            raise ValueError(f"Unsupported model: {model}")
        settings["model"] = model

    if "strict_mode_enabled" in settings_update:
        requested = bool(settings_update["strict_mode_enabled"])
        if not requested and is_strict_locked(settings):
            raise ValueError("Strict mode is locked until the selected time.")
        settings["strict_mode_enabled"] = requested

    if "strict_locked_until" in settings_update:
        locked_until = settings_update["strict_locked_until"]
        if locked_until:
            try:
                datetime.fromisoformat(locked_until)
            except Exception:
                raise ValueError("Strict lock time must be a valid ISO datetime.")
        settings["strict_locked_until"] = locked_until

    if "supervision_level" in settings_update:
        level = settings_update["supervision_level"]
        if level not in _valid_supervision_level_ids():
            raise ValueError(f"Unsupported supervision level: {level}")
        settings["supervision_level"] = level

    if "nudge_prompt" in settings_update:
        prompt = str(settings_update["nudge_prompt"] or "").strip()
        if not prompt:
            raise ValueError("提示语不能为空。")
        if len(prompt) > 500:
            raise ValueError("提示语不能超过 500 个字符。")
        settings["nudge_prompt"] = prompt

    if "default_check_interval_seconds" in settings_update:
        try:
            value = int(settings_update["default_check_interval_seconds"])
        except Exception:
            raise ValueError("默认检测间隔需要是整数秒。")
        if value < 5:
            raise ValueError("默认检测间隔不能少于 5 秒。")
        settings["default_check_interval_seconds"] = value

    if "trigger_threshold" in settings_update:
        try:
            value = int(settings_update["trigger_threshold"])
        except Exception:
            raise ValueError("触发答题命中次数需要是整数。")
        if value < 1:
            raise ValueError("触发答题命中次数不能少于 1。")
        settings["trigger_threshold"] = value

    if "whitelist_behaviors" in settings_update:
        behaviors = _normalize_string_list(settings_update["whitelist_behaviors"])
        if len(behaviors) > 50:
            raise ValueError("白名单最多支持 50 条行为描述。")
        if any(len(item) > 120 for item in behaviors):
            raise ValueError("单条白名单行为不能超过 120 个字符。")
        settings["whitelist_behaviors"] = behaviors

    if "guardian_mode_enabled" in settings_update:
        settings["guardian_mode_enabled"] = bool(settings_update["guardian_mode_enabled"])

    if "guardian_check_interval_seconds" in settings_update:
        try:
            value = int(settings_update["guardian_check_interval_seconds"])
        except Exception:
            raise ValueError("Guardian mode 检测间隔需要是整数秒。")
        if value < 30:
            raise ValueError("Guardian mode 检测间隔不能少于 30 秒。")
        settings["guardian_check_interval_seconds"] = value

    if "dataset_retention_days" in settings_update:
        value = settings_update["dataset_retention_days"]
        if value in (None, "", 0):
            settings["dataset_retention_days"] = None
        else:
            try:
                days = int(value)
            except Exception:
                raise ValueError("数据集保留天数需要是整数。")
            if days < 1:
                raise ValueError("数据集保留天数不能少于 1 天。")
            settings["dataset_retention_days"] = days

    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    return settings


def get_selected_model() -> str:
    return load_settings()["model"]


def get_default_strict_mode() -> bool:
    return bool(load_settings().get("strict_mode_enabled", True))


def get_supervision_level() -> str:
    return load_settings()["supervision_level"]


def get_nudge_prompt() -> str:
    return load_settings()["nudge_prompt"]


def get_default_check_interval_seconds() -> int:
    return int(load_settings()["default_check_interval_seconds"])


def get_default_trigger_threshold() -> int:
    return int(load_settings()["trigger_threshold"])


def get_whitelist_behaviors() -> list:
    return load_settings()["whitelist_behaviors"]


def is_guardian_mode_enabled() -> bool:
    return bool(load_settings().get("guardian_mode_enabled", True))


def get_guardian_check_interval_seconds() -> int:
    return int(load_settings()["guardian_check_interval_seconds"])


def _normalize_string_list(value) -> list:
    if isinstance(value, str):
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
    return normalized


def get_supervision_rules(level: str = None) -> str:
    selected = level or get_supervision_level()
    whitelist = get_whitelist_behaviors()
    whitelist_rules = "User-defined whitelist behaviors: none."
    if whitelist:
        whitelist_rules = (
            "User-defined whitelist behaviors. If the screenshot's main activity clearly matches one of these descriptions, mark on_task true, "
            "unless the activity is hard-blocked content:\n"
            + "\n".join(f"- {item}" for item in whitelist)
        )
    rules = {
        "task_related": (
            "Supervision level: TASK_RELATED.\n"
            f"{whitelist_rules}\n"
            "- Hard-blocked content always overrides the declared task and whitelist: porn/adult sexual content, reading novels/web novels, and reading manga/comics are off-task.\n"
            "- Mark on_task true only when the visible activity is clearly and strongly related to the declared task.\n"
            "- Short videos, social media, games, shopping, and unrelated browsing are off-task unless they clearly match a whitelist behavior."
        ),
        "not_entertainment": (
            "Supervision level: NOT_ENTERTAINMENT.\n"
            f"{whitelist_rules}\n"
            "- Hard-blocked content always overrides the declared task and whitelist: porn/adult sexual content, reading novels/web novels, and reading manga/comics are off-task.\n"
            "- Accept work, learning, writing, coding, planning, documentation, research, and other non-entertainment activities.\n"
            "- Short videos, social media, games, shopping, and obvious entertainment are off-task unless they clearly match a whitelist behavior.\n"
            "- If unsure and the screen is not clearly entertainment, give the user the benefit of the doubt."
        ),
    }
    return rules.get(selected, rules[DEFAULT_SETTINGS["supervision_level"]])


def is_strict_locked(settings: dict = None) -> bool:
    settings = settings or load_settings()
    if not settings.get("strict_mode_enabled"):
        return False
    locked_until = settings.get("strict_locked_until")
    if not locked_until:
        return False
    try:
        return datetime.now() < datetime.fromisoformat(locked_until)
    except Exception:
        return False


def get_strict_status() -> dict:
    settings = load_settings()
    return {
        "enabled": bool(settings.get("strict_mode_enabled")),
        "locked_until": settings.get("strict_locked_until"),
        "locked": is_strict_locked(settings),
    }


def get_settings_payload() -> dict:
    return {
        "settings": load_settings(),
        "model_options": MODEL_OPTIONS,
        "supervision_level_options": SUPERVISION_LEVEL_OPTIONS,
        "strict_status": get_strict_status(),
    }
