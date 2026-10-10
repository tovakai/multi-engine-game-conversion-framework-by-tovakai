#!/usr/bin/env python3
"""Desktop entry point for Multi-Engine Game Conversion Framework by Tovakai."""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from megcfbt.gui import main

if __name__ == "__main__":
    if '--verify-gui-conversion' in sys.argv[1:]:
        from megcfbt.gui_verification import main as verify_gui
        raise SystemExit(verify_gui())
    else:
        main()
