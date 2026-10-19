#!/usr/bin/env python3
"""Desktop entry point for Multi-Engine Game Conversion Framework by Tovakai."""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if __name__ == "__main__":
    if '--tls-diagnostics' in sys.argv[1:]:
        from megcfbt.tls_diagnostics import main as diagnose_tls
        raise SystemExit(diagnose_tls())
    elif any(flag in sys.argv[1:] for flag in ('--verify-gui-conversion', '--verify-gui-startup')):
        from megcfbt.gui_verification import main as verify_gui
        raise SystemExit(verify_gui())
    else:
        from megcfbt.gui import main
        main()
