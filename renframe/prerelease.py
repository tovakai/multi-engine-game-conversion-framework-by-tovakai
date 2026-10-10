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
        from renframe.bytecode_metadata import literal_assignments
        values = literal_assignments(root / 'renpy/vc_version.pyc')
        return bool(values.get('nightly') is True
                    and re.fullmatch(r'8\.5\.[0-4]\.\d+', str(values.get('version', '')))
                    and (root / 'game').is_dir() and (root / 'lib/python3.12').is_dir())
