import json
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

DEFAULT_SETTINGS = {
    "model": "google/gemini-2.5-flash-lite",
}


def _valid_model_ids() -> set:
    return {model["id"] for model in MODEL_OPTIONS}


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

    return settings


def save_settings(settings_update: dict) -> dict:
    settings = load_settings()

    if "model" in settings_update:
        model = settings_update["model"]
        if model not in _valid_model_ids():
            raise ValueError(f"Unsupported model: {model}")
        settings["model"] = model

    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    return settings


def get_selected_model() -> str:
    return load_settings()["model"]


def get_settings_payload() -> dict:
    return {
        "settings": load_settings(),
        "model_options": MODEL_OPTIONS,
    }
