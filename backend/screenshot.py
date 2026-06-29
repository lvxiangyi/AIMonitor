import os
from pathlib import Path

import mss
from PIL import Image


SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)


def take_screenshot(width: int = 768) -> str:
    """Take a screenshot, resize it, save as JPEG, and return the file path."""
    output_path = str(SCREENSHOT_DIR / "latest.jpg")

    with mss.mss() as sct:
        monitor = sct.monitors[0]  # Full virtual screen
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # Resize to save cost
    ratio = width / img.width
    new_height = int(img.height * ratio)
    img = img.resize((width, new_height), Image.LANCZOS)

    img.save(output_path, "JPEG", quality=70)
    return output_path
