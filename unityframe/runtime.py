"""Download and cache exact Unity and bridge archives; verify before every use."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from megcfbt.native_runtime import _cache_parent
from unityframe.prepare import digest


def profile():
    return json.loads(Path(__file__).with_name('profile.json').read_text(encoding='utf-8'))


def cached_archive(spec, target, *, progress=None, download_progress=None):
    target = Path(target)
    if target.is_file() and digest(target) == spec['sha256']:
        if progress:
            progress(f'Using verified cached runtime archive: {target.name}')
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f'.{target.name}.part-{uuid.uuid4().hex}')
    try:
        if progress:
            progress(f'Downloading {target.name}')
        request = urllib.request.Request(spec['url'], headers={'User-Agent': 'MEGCFBT-UnityFrame/0.1'})
        received = 0
        with urllib.request.urlopen(request, timeout=45) as response, temporary.open('xb') as output:
            size = response.headers.get('Content-Length')
            total = int(size) if size and size.isdigit() else None
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > spec.get('size', 512 * 1024 * 1024):
                    raise ValueError('Unity runtime download exceeded its size limit')
                output.write(chunk)
                if download_progress:
                    download_progress(received, total)
        if spec.get('size') is not None and received != spec['size']:
            raise ValueError('Unity runtime download size mismatch')
        if digest(temporary) != spec['sha256']:
            raise ValueError('Unity runtime SHA-256 mismatch; refusing the download')
        temporary.replace(target)
        return target
    except (OSError, urllib.error.URLError) as exc:
        raise ValueError(f'Could not download Unity runtime: {exc}') from exc
    finally:
        temporary.unlink(missing_ok=True)


def resolve_archives(runtime=None, *, progress=None, download_progress=None):
    recipe = profile()
    names = {'unity_package': 'UnitySetup-Windows-Mono-Support-for-Editor-6000.0.61f1.pkg',
             'bridge_package': 'bs-arm64-v0.3.2-proton-11.0-2c.tar.gz'}
    selected = runtime or os.environ.get('UNITYFRAME_RUNTIME')
    if selected is not None:
        directory = Path(selected).expanduser().resolve()
        result = []
        for key, name in names.items():
            path = directory / name
            if not path.is_file() or digest(path) != recipe[key]['sha256']:
                raise ValueError(f'Unity runtime override is missing a matching verified archive: {name}')
            result.append(path)
        return tuple(result)
    cache = _cache_parent() / 'unityframe' / recipe['id']
    return tuple(cached_archive(recipe[key], cache / name, progress=progress,
                                download_progress=download_progress) for key, name in names.items())
