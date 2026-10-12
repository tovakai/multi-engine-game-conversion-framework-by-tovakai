"""Validated native runtime SDK and owner-supplied FMOD library installation."""
import json
import os
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from celesteframe.profiles import PROFILE, digest
from megcfbt.native_backend import NativeBuildError, validate_runtime
from monoframe.runtime import windows_x64_executable
from renframe.elf import read_elf_architecture
from renframe.source_safety import validate_copy_tree

REQUIRED = {'dotnet/dotnet', 'managed/FNA.dll', 'managed/Steamworks.NET.dll',
            'prepare/windows-x64/CelestePrepare.exe', 'prepare/managed/CelestePrepare.dll',
            'native/libFNA3D.so', 'native/libFAudio.so.0', 'native/libtheorafile.so',
            'native/libSDL2-2.0.so.0', 'native/libsteam_api64.so',
            'native/libceleste_fmod_compat.so'}
FMOD_HASH = '48241c836b45116e1b25f9f2cb121e45c64140c5af205706b48c8b1c3712f963'
FMOD_FILENAME = 'fmodstudioapi20315linux.tar.gz'

def validate_fmod_sdk(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.stat().st_size != 76766958 or digest(path) != FMOD_HASH:
        raise NativeBuildError('Expected the checksum-verified FMOD Studio API 2.03.15 Linux SDK archive.')
    return path

def validate_sdk(root: Path) -> dict:
    root = root.resolve()
    try:
        validate_copy_tree(root)
        validate_runtime(root, 'dotnet/dotnet')
        manifest = json.loads((root/'engine-capabilities.json').read_text())
        if manifest.get('profile') != PROFILE or manifest.get('architecture') != 'aarch64':
            raise ValueError('Wrong Celeste runtime profile or architecture')
        files = manifest['files']
        runtime_files = manifest['runtime_files']
        if not isinstance(files, dict) or not REQUIRED.issubset(files):
            raise ValueError('Missing Celeste runtime or preparation files')
        if not isinstance(runtime_files, list) or not runtime_files or not set(runtime_files).issubset(files):
            raise ValueError('Invalid Celeste runtime file manifest')
        if not re.fullmatch(r'8\.0\.\d+', str(manifest.get('dotnet_version', ''))):
            raise ValueError('Expected the validated .NET 8 runtime')
        for name, expected in files.items():
            if (not isinstance(name, str) or '\\' in name or ':' in name
                or PurePosixPath(name).is_absolute() or any(part in {'', '.', '..'} for part in name.split('/'))
                or not re.fullmatch(r'[0-9a-f]{64}', str(expected))):
                raise ValueError('Unsafe Celeste SDK manifest')
            path = root/name
            if not path.is_file() or path.is_symlink() or digest(path) != expected:
                raise ValueError(f'Celeste SDK file failed checksum validation: {name}')
        if not windows_x64_executable(root/'prepare/windows-x64/CelestePrepare.exe'):
            raise ValueError('Expected the Windows x64 preparation tool')
        return manifest
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise NativeBuildError(f'Celeste runtime SDK validation failed: {error}') from error

def resolve_runtime(runtime=None, **kwargs):
    selected = runtime or os.environ.get('CELESTEFRAME_RUNTIME')
    if not selected:
        raise NativeBuildError('Celeste requires its matching Linux ARM64 SDK; select it with --backend-runtime.')
    root = Path(selected).expanduser().resolve()
    validate_sdk(root)
    return root

def automatic_runtime_available():
    return False

def find_fmod_sdk():
    selected = os.environ.get('MEGCFBT_CELESTE_FMOD_SDK')
    if selected:
        return validate_fmod_sdk(Path(selected))
    candidates = [Path.home()/'Downloads'/FMOD_FILENAME,
        Path(os.environ.get('APPDATA', Path.home()/'.config'))/'megcfbt/sts2/dependencies'/FMOD_FILENAME]
    for path in candidates:
        if path.is_file():
            try:
                return validate_fmod_sdk(path)
            except NativeBuildError:
                continue
    return None

def copy_runtime(sdk: Path, target: Path, fmod_sdk: Path):
    fmod_sdk = validate_fmod_sdk(fmod_sdk)
    manifest = validate_sdk(sdk)
    target.mkdir()
    for name in manifest['runtime_files']:
        destination = target/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sdk/name, destination)
    with tarfile.open(fmod_sdk) as archive:
        for directory, name in [('core', 'fmod'), ('studio', 'fmodstudio')]:
            member = archive.getmember(f'fmodstudioapi20315linux/api/{directory}/lib/arm64/lib{name}.so.14.15')
            if not member.isfile() or member.size > 32*1024*1024:
                raise NativeBuildError('Unexpected FMOD ARM64 SDK library')
            source = archive.extractfile(member)
            if source is None:
                raise NativeBuildError('Missing FMOD ARM64 SDK library')
            destination = target/'native'/f'lib{name}.so.14'
            with source, destination.open('wb') as output:
                shutil.copyfileobj(source, output)
            if read_elf_architecture(destination) != 'aarch64':
                raise NativeBuildError('FMOD library is not Linux ARM64')
    (target/'engine-capabilities.json').write_text(json.dumps({
        'profile': PROFILE, 'architecture': 'aarch64', 'purpose': 'owner-game-runtime',
        'fmod_sdk': fmod_sdk.name, 'dotnet_version': manifest['dotnet_version'],
        'files': {path.relative_to(target).as_posix(): digest(path)
                  for path in target.rglob('*') if path.is_file()}}, indent=2)+'\n')
