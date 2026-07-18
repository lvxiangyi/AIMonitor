import os
import sys
from pathlib import Path

import uvicorn


def _configure_tcl_tk():
    if not getattr(sys, "frozen", False):
        return

    base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    tcl_candidates = [
        base_dir / "_tcl_data",
        base_dir / "_tcl_data" / "tcl8.6",
        base_dir / "tcl8.6",
    ]
    tk_candidates = [
        base_dir / "_tk_data",
        base_dir / "_tk_data" / "tk8.6",
        base_dir / "tk8.6",
    ]

    for candidate in tcl_candidates:
        if (candidate / "init.tcl").exists():
            os.environ["TCL_LIBRARY"] = str(candidate)
            break

    for candidate in tk_candidates:
        if (candidate / "tk.tcl").exists():
            os.environ["TK_LIBRARY"] = str(candidate)
            break


_configure_tcl_tk()

from main import app


def main():
    port = int(os.getenv("FOCUSGUARD_PORT", "8899"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
