import os
from datetime import datetime
from typing import Optional

from settings_manager import get_selected_model


_last_success_at: Optional[str] = None
_last_error_at: Optional[str] = None
_last_error: Optional[str] = None
_last_model: Optional[str] = None


def is_mock_enabled() -> bool:
    return os.getenv("AIMONITOR_ENABLE_MOCK_AI", "").strip().lower() in {"1", "true", "yes", "on"}


def has_api_key() -> bool:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    return bool(key and key != "your_api_key_here")


def record_ai_success(model: str):
    global _last_success_at, _last_error, _last_model
    _last_success_at = datetime.now().isoformat()
    _last_error = None
    _last_model = model


def record_ai_error(error: str, model: str = ""):
    global _last_error_at, _last_error, _last_model
    _last_error_at = datetime.now().isoformat()
    _last_error = error
    _last_model = model or _last_model


def get_ai_status() -> dict:
    model = get_selected_model()
    mock_enabled = is_mock_enabled()
    key_present = has_api_key()

    if mock_enabled:
        state = "mock"
        message = "Mock 模式已开启，AI 判定会使用测试数据。"
    elif not key_present:
        state = "unconfigured"
        message = "未配置有效的 OpenRouter API Key。"
    elif _last_error:
        state = "error"
        message = _last_error
    elif _last_success_at:
        state = "connected"
        message = "AI 连接正常。"
    else:
        state = "unknown"
        message = "尚未完成过 AI 判定。"

    return {
        "state": state,
        "message": message,
        "model": model,
        "key_present": key_present,
        "mock_enabled": mock_enabled,
        "last_success_at": _last_success_at,
        "last_error_at": _last_error_at,
        "last_error": _last_error,
        "last_model": _last_model,
    }
