"""Resolve native SDK bundles configured once for repeated conversions."""
from pathlib import Path
import os


def configured_runtime(engine: str) -> Path | None:
    configured = os.environ.get(engine.upper()+'FRAME_RUNTIME')
    if configured:
        return Path(configured).expanduser().resolve()
    parent = os.environ.get('MEGCFBT_NATIVE_RUNTIME_DIR')
    if parent:
        candidate = Path(parent).expanduser()/engine
    elif os.name == 'nt':
        candidate = Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'tovakai/cache/runtimes/native'/engine
    else:
        candidate = Path.home()/'.cache/tovakai/runtimes/native'/engine
    return candidate.resolve() if candidate.is_dir() else None
