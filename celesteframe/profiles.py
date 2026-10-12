"""Identity gate for the audited vanilla Steam Windows XNA installation."""
import hashlib
from pathlib import Path

PROFILE = 'celeste-steam-xna-1.4.0.0'
SOURCE_HASHES = {
    'Celeste.exe': '1a1e117add967c0f26ad470a49d4ff442435209265bf1fdda623821d797e80b5',
    'Steamworks.NET.dll': '6c6b307e907294003014da3ed4610e362a9b6ee4093a20e514b0e23454da3085',
    'CSteamworks.dll': '7f08cfc5b685c8f44b34a6fd4500fb136b9c5ab3faba975565dbf8ca308a4551',
    'steam_api.dll': 'af17df745250d1814eaa274fff7b0faeb43381e6762e026267e5859778477abd',
    'fmod.dll': 'a8db3942bb5043e5bf425ee71c73ddd43ff1798faa2313960d59ab1148d95aba',
    'fmodstudio.dll': 'c2dfc4305b175053552301bc3820732c0eb7369859d1959d17d10a1c8b010b19',
}

def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()

def matches_source(root: Path) -> bool:
    if not (root/'Content/FMOD').is_dir() or not (root/'Content/Maps').is_dir():
        return False
    if any((root/name).exists() for name in ('Mods', 'Celeste.Mod.mm.dll', 'Everest.dll')):
        return False
    try:
        return all(digest(root/name) == expected for name, expected in SOURCE_HASHES.items())
    except OSError:
        return False
