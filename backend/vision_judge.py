import os
import json
import base64
import random

from openai import OpenAI
from dotenv import load_dotenv
from ai_status_manager import (
    has_api_key,
    is_mock_enabled,
    record_ai_error,
    record_ai_success,
)
from settings_manager import get_selected_model, get_supervision_rules
from data_paths import ENV_FILE

load_dotenv(dotenv_path=ENV_FILE)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

PROMPT_TEMPLATE = """You are a focus monitoring agent.

The user's declared task is:
"{task}"

{memory_context}

Look at the screenshot and judge whether the user is currently working on the declared task.

{supervision_rules}

Important rules:
- If the user is reading novels, reading manga/comics, viewing porn/adult websites, watching short videos, using social media, consuming entertainment content, playing games, shopping, or using unrelated websites, mark on_task as false unless the supervision rules explicitly allow it.
- If the user is reading documents, writing notes, using educational websites, coding related to the task, or solving problems related to the declared task, mark on_task as true.
- If unsure, use the screenshot content and the user's declared task to make the best judgement.
- Be strict but reasonable.
- IMPORTANT: Consider the learned exceptions listed above. If the current activity matches a previously accepted exception, mark on_task as true.

Return JSON only:
{{
  "on_task": true or false,
  "confidence": number between 0 and 1,
  "current_activity": "short description of what the user is doing",
  "reason": "short explanation"
}}"""


DISPUTE_PROMPT_TEMPLATE = """You are a focus monitoring agent that is evaluating a user's dispute.

The user's declared task is: "{task}"

The AI previously judged the user as OFF-TASK:
- Detected activity: "{activity}"
- AI's reason: "{original_reason}"

The user disagrees and says:
"{user_reason}"

{memory_context}

Please evaluate:
1. Is the user's explanation reasonable? Could their current activity actually be related to the declared task?
2. Be fair - if the user provides a reasonable explanation, accept it.
3. But don't accept obviously false excuses.

Return JSON only:
{{
  "accepted": true or false,
  "ai_reason": "short explanation of why you accepted or rejected the dispute"
}}"""


GUARDIAN_PROMPT_TEMPLATE = """You are Guardian mode for a local focus assistant.

Guardian mode is always-on and only detects obvious entertainment or adult distractions.
It does not judge whether work is related to a declared task.

{whitelist_context}

Look at the screenshot and decide whether Guardian mode should interrupt the user.

Interrupt only for clearly visible:
- porn or adult sexual content
- reading novels or web novels for entertainment
- reading manga or comics for entertainment
- playing or watching games as entertainment

These are OR conditions. If any one category is clearly visible, set should_interrupt=true.
Adult/sexual content is only one category; novels, web novels, manga, comics, and games do not need to be adult/sexual to trigger.

Do not interrupt for normal work, study, coding, writing, documentation, chat about work, music players, timers, utilities, or ambiguous screens.
If a visible activity clearly matches the user-defined whitelist, do not interrupt unless it also clearly falls into one of the four interrupt categories above.
If unsure, do not interrupt.

Return JSON only:
{{
  "should_interrupt": true or false,
  "trigger_category": "adult" or "novel" or "manga" or "game" or "none",
  "confidence": number between 0 and 1,
  "current_activity": "short description of what the user is doing",
  "reason": "short explanation"
}}

Meaning:
- should_interrupt=true only for the explicit Guardian categories above.
- should_interrupt=true when trigger_category is adult, novel, manga, or game.
- should_interrupt=false for papers, articles, search pages, normal work/study, ambiguous reading, or anything that is not clearly entertainment/adult content.
"""


def _format_memory_context(memory: list) -> str:
    """Format dispute memory into context for the prompt."""
    if not memory:
        return ""

    lines = ["Previously learned exceptions (activities the user has explained are actually on-task):"]
    for entry in memory[-10:]:  # Last 10 entries to avoid too long context
        lines.append(f"- Activity: \"{entry.get('activity', '')}\" → Reason: \"{entry.get('user_reason', '')}\"")

    return "\n".join(lines)


def _format_whitelist_context() -> str:
    from settings_manager import get_whitelist_behaviors

    whitelist = get_whitelist_behaviors()
    if not whitelist:
        return "User-defined whitelist behaviors: none."
    lines = ["User-defined whitelist behaviors:"]
    lines.extend(f"- {item}" for item in whitelist)
    return "\n".join(lines)


def _mock_judge(task: str) -> dict:
    """Mock mode: randomly return on_task or off_task for testing."""
    on_task = random.random() > 0.4
    activities_on = [
        "reading study materials",
        "writing notes in a document",
        "viewing educational content",
        "solving practice problems",
    ]
    activities_off = [
        "watching YouTube Shorts",
        "browsing social media",
        "playing a game",
        "shopping online",
    ]

    if on_task:
        activity = random.choice(activities_on)
        reason = f"The user appears to be engaged in activities related to '{task}'."
    else:
        activity = random.choice(activities_off)
        reason = f"The user is doing '{activity}' which is unrelated to '{task}'."

    return {
        "on_task": on_task,
        "confidence": round(random.uniform(0.6, 0.95), 2),
        "current_activity": activity,
        "reason": reason,
        "judgement_status": "mock",
        "model": "mock",
    }


def _api_error_result(task: str, error: str, model: str = "") -> dict:
    return {
        "on_task": True,
        "confidence": 0,
        "current_activity": "AI 判定不可用",
        "reason": f"AI 连接失败，本次检查已暂停判定：{error}",
        "judgement_status": "api_error",
        "error": error,
        "model": model or "api-error",
    }


def _get_client():
    """Get OpenAI client configured for OpenRouter."""
    return OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
    )


def judge_screenshot(task: str, screenshot_path: str, memory: list = None, supervision_level: str = None) -> dict:
    """Judge whether the user is on task based on a screenshot."""
    model = get_selected_model()

    if is_mock_enabled():
        print("[vision_judge] AIMONITOR_ENABLE_MOCK_AI is enabled, using mock mode.")
        return _mock_judge(task)

    if not has_api_key():
        error = "No valid OpenRouter API key configured."
        print(f"[vision_judge] {error}")
        record_ai_error(error, model=model)
        return _api_error_result(task, error, model=model)

    memory_context = _format_memory_context(memory or [])
    supervision_rules = get_supervision_rules(supervision_level)

    try:
        client = _get_client()
        print(f"[vision_judge] Using model: {model}")

        with open(screenshot_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": PROMPT_TEMPLATE.format(
                                task=task,
                                memory_context=memory_context,
                                supervision_rules=supervision_rules,
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}",
                                "detail": "low",
                            },
                        },
                    ],
                }
            ],
            max_tokens=300,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("```", 1)[0]

        result = json.loads(content)
        result["model"] = model
        result["judgement_status"] = "ok"
        record_ai_success(model)
        return result

    except Exception as e:
        error = str(e)
        print(f"[vision_judge] Error calling OpenRouter API: {error}")
        print("[vision_judge] Pausing this judgement instead of using random mock mode.")
        record_ai_error(error, model=model)
        return _api_error_result(task, error, model=model)


def judge_guardian_screenshot(screenshot_path: str) -> dict:
    """Judge whether always-on Guardian mode should interrupt obvious entertainment."""
    model = get_selected_model()

    if is_mock_enabled():
        result = _mock_judge("Guardian mode")
        result["on_task"] = bool(result.get("on_task", True))
        return result

    if not has_api_key():
        error = "No valid OpenRouter API key configured."
        print(f"[vision_judge] {error}")
        record_ai_error(error, model=model)
        return _api_error_result("Guardian mode", error, model=model)

    try:
        client = _get_client()
        print(f"[vision_judge] Using model for guardian: {model}")

        with open(screenshot_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": GUARDIAN_PROMPT_TEMPLATE.format(
                                whitelist_context=_format_whitelist_context()
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}",
                                "detail": "low",
                            },
                        },
                    ],
                }
            ],
            max_tokens=250,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("```", 1)[0]

        result = json.loads(content)
        if "should_interrupt" in result:
            result["on_task"] = not bool(result["should_interrupt"])
        category = str(result.get("trigger_category", "none")).strip().lower()
        if category in {"adult", "novel", "manga", "game"}:
            result["should_interrupt"] = True
            result["on_task"] = False
        elif "should_interrupt" not in result:
            result["should_interrupt"] = not bool(result.get("on_task", True))
        result["model"] = model
        result["judgement_status"] = "ok"
        record_ai_success(model)
        return result

    except Exception as e:
        error = str(e)
        print(f"[vision_judge] Guardian error calling OpenRouter API: {error}")
        record_ai_error(error, model=model)
        return _api_error_result("Guardian mode", error, model=model)


def evaluate_dispute(task: str, activity: str, original_reason: str, user_reason: str, memory: list = None) -> dict:
    """Evaluate a user's dispute against an AI judgement."""
    if is_mock_enabled():
        print("[vision_judge] No valid API key, auto-accepting dispute in mock mode.")
        return {"accepted": True, "ai_reason": "Mock mode: dispute auto-accepted."}

    if not has_api_key():
        return {"accepted": True, "ai_reason": "AI 未连接，默认接受本次异议。"}

    memory_context = _format_memory_context(memory or [])

    try:
        client = _get_client()
        model = get_selected_model()
        print(f"[vision_judge] Using model for dispute: {model}")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": DISPUTE_PROMPT_TEMPLATE.format(
                        task=task,
                        activity=activity,
                        original_reason=original_reason,
                        user_reason=user_reason,
                        memory_context=memory_context,
                    ),
                }
            ],
            max_tokens=200,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("```", 1)[0]

        result = json.loads(content)
        return result

    except Exception as e:
        print(f"[vision_judge] Dispute evaluation error: {e}")
        # On error, give user benefit of doubt
        return {"accepted": True, "ai_reason": f"Error during evaluation, accepting dispute. ({e})"}
