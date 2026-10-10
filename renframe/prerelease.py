"""Narrow explicit full-engine migration for Ren'Py 8.5 nightlies."""
from pathlib import Path
import re


def prerelease_853_candidate(root: Path) -> bool:
    try:
        text = (root / 'renpy/vc_version.py').read_text(encoding='utf-8')
        return bool(re.search(r'(?m)^nightly\s*=\s*True\s*$', text)
                    and re.search(r"(?m)^version\s*=\s*['\"]8\.5\.[0-4]\.\d+['\"]", text)
                    and (root / 'game').is_dir()
                    and (root / 'lib/python3.12').is_dir())
    except (OSError, UnicodeError):
        return False
