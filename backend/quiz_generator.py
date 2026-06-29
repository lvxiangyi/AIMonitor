"""
Quiz generator: generates questions related to the user's task.
When the user is distracted, they must answer a quiz to continue.
Wrong answers are recorded for review.
"""

import os
import json
import random
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

LOGS_DIR = Path(__file__).parent.parent / "logs"
WRONG_ANSWERS_FILE = LOGS_DIR / "wrong_answers.json"

QUIZ_PROMPT = """You are a quiz generator for a study assistant app.

The user's study task is: "{task}"

Generate ONE quiz question related to this study topic.
The question should be educational and help reinforce the subject matter.
Difficulty: medium.

IMPORTANT: Generate the question and all options in Japanese (日本語).

Return JSON only:
{{
  "question": "問題文（日本語）",
  "options": ["選択肢A", "選択肢B", "選択肢C", "選択肢D"],
  "correct_index": 0,
  "explanation": "正解の説明（日本語）"
}}

Important:
- correct_index is 0-based (0=A, 1=B, 2=C, 3=D)
- Make the question specific and educational
- All options should be plausible
- Everything must be in Japanese
"""

# Fallback quiz bank for common topics
FALLBACK_QUIZZES = {
    "math": [
        {
            "question": "∫ 2x dx の結果は？",
            "options": ["x² + C", "2x² + C", "x + C", "2x + C"],
            "correct_index": 0,
            "explanation": "∫ 2x dx = x² + C（積分定数）"
        },
        {
            "question": "lim(x→0) sin(x)/x の値は？",
            "options": ["1", "0", "∞", "不定"],
            "correct_index": 0,
            "explanation": "これは有名な極限で、値は1です。"
        },
        {
            "question": "行列 [[1,0],[0,1]] は何と呼ばれますか？",
            "options": ["単位行列", "零行列", "転置行列", "逆行列"],
            "correct_index": 0,
            "explanation": "対角成分が1、他が0の行列は単位行列（Identity Matrix）です。"
        },
        {
            "question": "dy/dx = 2x のとき、y = ?",
            "options": ["x² + C", "2x² + C", "x + C", "2"],
            "correct_index": 0,
            "explanation": "両辺を積分すると y = x² + C"
        },
        {
            "question": "三角形の内角の和は？",
            "options": ["180°", "360°", "90°", "270°"],
            "correct_index": 0,
            "explanation": "三角形の内角の和は常に180°です。"
        },
    ],
    "default": [
        {
            "question": "集中力を保つために最も効果的な方法は？",
            "options": ["25分作業+5分休憩（ポモドーロ）", "3時間連続作業", "BGMを大音量で流す", "SNSを開いたまま作業"],
            "correct_index": 0,
            "explanation": "ポモドーロ・テクニックは科学的に集中力維持に効果があることが示されています。"
        },
        {
            "question": "人間の短期記憶の容量は約何個？",
            "options": ["7±2個", "3±1個", "20±5個", "100個以上"],
            "correct_index": 0,
            "explanation": "ミラーの法則により、短期記憶は約7±2個の情報を保持できます。"
        },
    ]
}


def _load_wrong_answers() -> list:
    if WRONG_ANSWERS_FILE.exists():
        try:
            with open(WRONG_ANSWERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_wrong_answers(answers: list):
    with open(WRONG_ANSWERS_FILE, "w", encoding="utf-8") as f:
        json.dump(answers, f, ensure_ascii=False, indent=2)


def record_wrong_answer(question: str, user_answer: str, correct_answer: str, task: str):
    """Record a wrong answer for later review."""
    answers = _load_wrong_answers()
    answers.append({
        "question": question,
        "user_answer": user_answer,
        "correct_answer": correct_answer,
        "task": task,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    })
    _save_wrong_answers(answers)


def get_wrong_answers() -> list:
    """Get all recorded wrong answers."""
    return _load_wrong_answers()


def generate_quiz(task: str) -> dict:
    """Generate a quiz question related to the user's task."""
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_api_key_here":
        return _fallback_quiz(task)

    try:
        client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "user", "content": QUIZ_PROMPT.format(task=task)}
            ],
            max_tokens=300,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("```", 1)[0]

        result = json.loads(content)
        return result

    except Exception as e:
        print(f"[quiz_generator] Error: {e}, using fallback")
        return _fallback_quiz(task)


def _fallback_quiz(task: str) -> dict:
    """Return a fallback quiz from the bank."""
    task_lower = task.lower()
    if any(w in task_lower for w in ["math", "数学", "calculus", "微積分", "線形代数"]):
        quizzes = FALLBACK_QUIZZES["math"]
    else:
        quizzes = FALLBACK_QUIZZES["default"]
    return random.choice(quizzes)
