import ctypes
import os
from ctypes import wintypes
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import mss
from PIL import Image

from data_paths import SCREENSHOT_DIR


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def _get_cursor_position() -> Optional[Tuple[int, int]]:
    """Return the current Windows cursor position in virtual-screen coordinates."""
    try:
        point = POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return point.x, point.y
    except Exception as e:
        print(f"[screenshot] Could not read cursor position: {e}")
    return None


def _monitor_contains_point(monitor: Dict, x: int, y: int) -> bool:
    return (
        monitor["left"] <= x < monitor["left"] + monitor["width"]
        and monitor["top"] <= y < monitor["top"] + monitor["height"]
    )


def _select_monitor(monitors: List[Dict]) -> Dict:
    mode = os.getenv("AIMONITOR_SCREENSHOT_MODE", "cursor").strip().lower()

    if mode == "full":
        print("[screenshot] Capturing full virtual screen because AIMONITOR_SCREENSHOT_MODE=full.")
        return monitors[0]

    cursor_pos = _get_cursor_position()
    if cursor_pos:
        x, y = cursor_pos
        for monitor in monitors[1:]:
            if _monitor_contains_point(monitor, x, y):
                print(
                    "[screenshot] Capturing monitor at "
                    f"left={monitor['left']} top={monitor['top']} "
                    f"width={monitor['width']} height={monitor['height']} "
                    f"for cursor=({x},{y})."
                )
                return monitor

        print(f"[screenshot] Cursor position {cursor_pos} did not match a monitor; using primary monitor.")

    return monitors[1] if len(monitors) > 1 else monitors[0]


def take_screenshot(width: int = 768, output_path: Optional[str] = None) -> str:
    """Take a screenshot of the cursor's monitor, resize it, and return the file path."""
    output = Path(output_path) if output_path else SCREENSHOT_DIR / "latest.jpg"
    output.parent.mkdir(parents=True, exist_ok=True)

    with mss.mss() as sct:
        monitor = _select_monitor(sct.monitors)
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # Resize to save cost
    ratio = width / img.width
    new_height = int(img.height * ratio)
    img = img.resize((width, new_height), Image.LANCZOS)

    img.save(str(output), "JPEG", quality=70)
    return str(output)
