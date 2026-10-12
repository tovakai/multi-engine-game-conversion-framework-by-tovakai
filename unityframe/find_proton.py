"""Find an installed, supported ARM64 Proton without changing Steam settings."""
from __future__ import annotations

import os
import re
from pathlib import Path


SUPPORTED = {'proton-11.0-2c-arm64', 'proton-11.0-2e-arm64',
             'proton-11.0-2c', 'proton-11.0-2e'}


def steam_roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    roots = [home / '.steam/steam', home / '.local/share/Steam']
    if os.environ.get('HK_ARM64_STEAM_ROOT'):
        roots.insert(0, Path(os.environ['HK_ARM64_STEAM_ROOT']).expanduser())
    for root in list(roots):
        try:
            data = (root / 'steamapps/libraryfolders.vdf').read_text(encoding='utf-8')
        except OSError:
            continue
        roots.extend(Path(path) for path in re.findall(r'"path"\s+"([^"]+)"', data))
    return list(dict.fromkeys(path.resolve() for path in roots))


def find_proton(home: Path | None = None) -> Path:
    for root in steam_roots(home):
        for version in sorted((root / 'steamapps/common').glob('*/version')):
            try:
                fields = version.read_text(encoding='utf-8').split()
                if len(fields) < 2 or fields[1] not in SUPPORTED:
                    continue
                directory = version.parent
                if (directory / 'proton').is_file() and (directory / 'files/lib/wine/aarch64-unix/lsteamclient.so').is_file():
                    return directory
            except OSError:
                continue
    raise ValueError('Install a supported ARM64 Proton 11.0 through Steam, or set HK_ARM64_PROTON to its directory.')


if __name__ == '__main__':
    try:
        print(find_proton())
    except ValueError as exc:
        raise SystemExit(str(exc))
