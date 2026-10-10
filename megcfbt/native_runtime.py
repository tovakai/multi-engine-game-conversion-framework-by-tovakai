"""Resolve native SDK bundles configured once for repeated conversions."""
from pathlib import Path
import os
import hashlib,json,re

EXECUTABLES={'gamemaker':'butterscotch','love':'love','ags':'ags','easyrpg':'easyrpg-player'}
INDEX_PATH=Path(__file__).resolve().parent/'native_runtime_index.json'


def recipe_entry(engine: str) -> dict | None:
    if engine not in EXECUTABLES:return None
    try:
        entry=json.loads(INDEX_PATH.read_text(encoding='utf-8'))['recipes'][engine]
    except (OSError,ValueError,KeyError,TypeError):return None
    if not isinstance(entry,dict):return None
    if (not isinstance(entry.get('url'),str) or not entry['url'].startswith(
        'https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/')
        or not re.fullmatch('[0-9a-fA-F]{64}',str(entry.get('sha256','')))
        or entry.get('executable')!=EXECUTABLES[engine]
        or not re.fullmatch('[a-z0-9-]+',str(entry.get('recipe_id','')))):return None
    files=entry.get('archive_files')
    if (not isinstance(files,list) or not all(isinstance(name,str) and re.fullmatch('[A-Za-z0-9_+.-]+',name)
            and name not in {'.','..'} for name in files)
        or len(files)!=len(set(files)) or not {entry['executable'],'engine-capabilities.json'}.issubset(files)):
        return None
    return entry


def automatic_runtime_available(engine: str) -> bool:
    return recipe_entry(engine) is not None


def _cache_parent() -> Path:
    configured=os.environ.get('MEGCFBT_NATIVE_RUNTIME_DIR')
    if configured:return Path(configured).expanduser().resolve()
    shared=os.environ.get('RPGMFRAME_CACHE_DIR')
    if shared:return Path(shared).expanduser().resolve()/'runtimes/native'
    if os.name=='nt':return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'tovakai/cache/runtimes/native'
    return Path.home()/'.cache/tovakai/runtimes/native'


def _validate(path: Path, entry: dict) -> bool:
    from megcfbt.native_backend import validate_runtime,NativeBuildError
    try:
        data=json.loads((path/'engine-capabilities.json').read_text())
        if not isinstance(data,dict) or data.get('recipe_id')!=entry['recipe_id'] or data.get('architecture')!='aarch64':return False
        hashes=data.get('files')
        if not isinstance(hashes,dict):return False
        for name in entry['archive_files']:
            if name=='engine-capabilities.json':continue
            file=path/name
            if not file.is_file() or hashes.get(name)!=hashlib.sha256(file.read_bytes()).hexdigest():return False
        validate_runtime(path,entry['executable'])
        return True
    except (OSError,ValueError,TypeError,NativeBuildError):return False


def resolve_runtime(engine: str, runtime=None, *, progress=None, download_progress=None) -> Path:
    from megcfbt.native_backend import NativeBuildError
    from megcfbt.runtime_download import ensure_bundle,RuntimeDownloadError
    selected=Path(runtime).expanduser().resolve() if runtime is not None else configured_runtime(engine)
    if selected is not None:return selected
    entry=recipe_entry(engine)
    if entry is None:raise NativeBuildError(f'No published ARM64 runtime recipe for {engine}; select a compatible manual runtime.')
    target=_cache_parent()/engine/entry['recipe_id']
    try:
        return ensure_bundle(entry,target,validate=lambda path:_validate(path,entry),progress=progress,download_progress=download_progress)
    except RuntimeDownloadError as exc:raise NativeBuildError(str(exc)) from exc


def configured_runtime(engine: str) -> Path | None:
    if engine not in EXECUTABLES:return None
    configured = os.environ.get(engine.upper()+'FRAME_RUNTIME')
    if configured:
        return Path(configured).expanduser().resolve()
    candidate = _cache_parent()/engine
    return candidate.resolve() if (candidate/EXECUTABLES[engine]).is_file() else None
