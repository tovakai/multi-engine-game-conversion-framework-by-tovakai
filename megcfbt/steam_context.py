"""Recover numeric Steam application metadata without executing game code."""
from pathlib import Path
import json
import re


def steam_app_id_for_source(source: Path) -> str | None:
    def valid(value):
        text = str(value).strip()
        return text if text.isascii() and text.isdecimal() and 0 < int(text) < 2**32 else None

    sidecar = source / 'steam_appid.txt'
    try:
        if sidecar.is_file() and sidecar.stat().st_size <= 32:
            value = valid(sidecar.read_text(encoding='ascii'))
            if value:
                return value
        data = source / 'steam_data.json'
        if data.is_file() and data.stat().st_size <= 65536:
            values = json.loads(data.read_text(encoding='utf-8'))
            value = valid(values.get('app_id')) if isinstance(values, dict) else None
            if value:
                return value
    except (OSError, ValueError, UnicodeError):
        pass
    # Steam's installed-game manifest is outside the game directory. Match
    # installdir explicitly, including exports nested beneath that directory.
    for common in source.parents:
        if common.name.casefold() != 'common' or common.parent.name.casefold() != 'steamapps':
            continue
        installed_name = source.relative_to(common).parts[0]
        for manifest in common.parent.glob('appmanifest_*.acf'):
            try:
                if manifest.stat().st_size > 65536:
                    continue
                text = manifest.read_text(encoding='utf-8')
                folder = re.search(r'"installdir"\s+"([^"\\]*)"', text, re.I)
                appid = re.search(r'"appid"\s+"(\d+)"', text, re.I)
                if folder and appid and folder.group(1).casefold() == installed_name.casefold():
                    return valid(appid.group(1))
            except (OSError, UnicodeError):
                continue
    return None


def write_steam_app_id(app_id: str, *folders: Path) -> None:
    for folder in folders:
        (folder / 'steam_appid.txt').write_text(app_id + '\n',encoding='ascii')
