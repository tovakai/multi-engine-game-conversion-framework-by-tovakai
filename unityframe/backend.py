"""Exact-edition Hollow Knight backend for the unified converter."""
from __future__ import annotations

from dataclasses import replace
import tarfile
import json
import shutil
import uuid
from pathlib import Path
import pefile

from megcfbt.models import UnifiedBuildResult
from megcfbt.native_backend import NativeBuildError
from megcfbt.steam_context import write_steam_app_id
from megcfbt.unity import inspect_game as inspect_unity
from unityframe.prepare import prepare, verify_source
from unityframe.runtime import profile, resolve_archives


def inspect_game(root):
    if not (root / 'hollow_knight_Data/Managed/Assembly-CSharp.dll').is_file() or not (root / 'hollow_knight.exe').is_file():
        return None
    summary = inspect_unity(root)
    if summary is None or summary.engine_version != profile()['engine_version']:
        return None
    try:
        verify_source(root, profile())
    except (OSError, ValueError, pefile.PEFormatError):
        return None
    return replace(summary, backend='unityframe', buildable=True, compatibility='needs_testing',
                   runtime_kind='Windows ARM64 / ARM64 Proton 11.0 (automatic runtime downloads)',
                   warnings=('Experimental Hollow Knight profile: menu, controller gameplay, audio and bench save/load after relaunch verified on Frame.',
                             'Requires supported ARM64 Proton 11.0 on the target. Vibration, achievements and longer gameplay need testing.'),
                   evidence=tuple(item for item in summary.evidence if 'research candidate' not in item)
                            + (f'Exact source identities match {profile()["id"]}',))


def build_game(source, *, output, runtime=None, runtime_version=None, force=False,
               progress=None, download_progress=None, steam_app_id=None):
    try:
        return _build_game(source, output=output, runtime=runtime, runtime_version=runtime_version,
                           force=force, progress=progress, download_progress=download_progress,
                           steam_app_id=steam_app_id)
    except (OSError, ValueError, pefile.PEFormatError, tarfile.TarError) as exc:
        raise NativeBuildError(str(exc)) from exc


def _build_game(source, *, output, runtime=None, runtime_version=None, force=False,
                progress=None, download_progress=None, steam_app_id=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError('Unity output must be separate from the original installation')
    verify_source(source, profile())
    if output.exists():
        if not force:
            raise ValueError('Unity output already exists; select a new directory or use --force.')
        if (output / '.hk-arm64/compatdata').exists():
            raise ValueError('This output contains a Proton prefix and saves; select a new output directory to preserve them.')
        try:
            previous = json.loads((output / '.hk-arm64/manifest.json').read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ValueError('Refusing to replace an output without a matching UnityFrame manifest') from exc
        if previous.get('profile') != profile()['id']:
            raise ValueError('Existing output belongs to a different Unity profile')
    if runtime_version is not None and runtime_version != profile()['engine_version']:
        raise ValueError('Hollow Knight requires the exact pinned Unity engine version')
    unity, bridge = resolve_archives(runtime, progress=progress, download_progress=download_progress)
    if progress:
        progress('Preparing verified Hollow Knight Windows ARM64 runtime and game copy')
    backup = output.with_name(f'.{output.name}-unityframe-old-{uuid.uuid4().hex}')
    if output.exists():
        output.rename(backup)
    try:
        prepare(source, unity, bridge, output)
    except Exception:
        if backup.exists() and not output.exists():
            backup.rename(output)
        raise
    if backup.exists():
        if backup.resolve().parent != output.parent or not backup.name.startswith(f'.{output.name}-unityframe-old-'):
            raise ValueError('Refusing cleanup outside the output parent')
        shutil.rmtree(backup)
    write_steam_app_id('367520', output)
    launcher = output / 'launch-hollow-knight-arm64.sh'
    from megcfbt.frame_package import write_frame_metadata
    write_frame_metadata(output, name='Hollow Knight', launcher_path=launcher, engine='unity',
                         engine_version=inspect_unity(source).engine_version,
                         runtime_engine_version=profile()['engine_version'],
                         compatibility_profile=profile()['id'], target_platform='windows-arm64-proton')
    return UnifiedBuildResult(source, output, launcher, None, 'unityframe', 'unity',
                              profile()['engine_version'], 'Hollow Knight',
                              ('Experimental Windows ARM64 build for ARM64 Proton; install a supported ARM64 Proton 11.0 on the target.',),
                              target_platform='windows-arm64-proton')
