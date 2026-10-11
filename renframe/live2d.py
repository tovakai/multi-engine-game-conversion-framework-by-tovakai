"""Import a user-supplied Live2D native core; never accept vendor terms or download it."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import shutil
import tempfile
import zipfile
from renframe.elf import read_elf_architecture

DOWNLOAD_URL = 'https://www.live2d.com/en/sdk/download/native/'
NAME = 'libLive2DCubismCore.so'


def required(root: Path) -> bool:
    game = root / 'game'
    return (any(game.rglob('*.moc3')) or any(game.rglob('*.model3.json'))
            or any((root / 'lib').rglob('Live2DCubismCore.dll')))


def cache_root() -> Path:
    from renframe.runtime import _default_cache_dir
    return _default_cache_dir() / 'dependencies/live2d'


def validate(path: Path) -> Path:
    if path.is_symlink() or getattr(path, 'is_junction', lambda: False)() or read_elf_architecture(path) != 'aarch64':
        raise ValueError('Live2D Core must be a regular Linux ARM64 ELF library.')
    return path


def import_sdk(archive_path: Path) -> Path:
    """Select only Linux ARM64 Core and its notice from an already downloaded SDK."""
    if not archive_path.is_file() or archive_path.is_symlink():
        raise ValueError('Select the downloaded Cubism SDK for Native ZIP.')
    with zipfile.ZipFile(archive_path) as archive:
        matches = [i for i in archive.infolist() if i.filename.casefold().endswith('/core/dll/experimental/linux/arm64/' + NAME.casefold())
                   or i.filename.casefold().endswith('/core/dll/linux/arm64/' + NAME.casefold())]
        if len(matches) != 1:
            raise ValueError('SDK must contain exactly one Linux ARM64 Cubism Core library; Android ARM64 is incompatible.')
        member = matches[0]
        if '..' in PurePosixPath(member.filename).parts or '\\' in member.filename or member.file_size > 32 * 1024 * 1024:
            raise ValueError('Invalid Live2D SDK member.')
        mode = member.external_attr >> 16
        if mode & 0o170000 == 0o120000:
            raise ValueError('SDK library must not be a symbolic link.')
        data = archive.read(member)
        notices = [i for i in archive.infolist() if i.filename.endswith('/Core/LICENSE.md')]
        if len(notices) != 1 or notices[0].file_size > 1024 * 1024:
            raise ValueError('SDK is missing its Cubism Core license notice.')
        notice = archive.read(notices[0])
    digest = hashlib.sha256(data).hexdigest()
    root = cache_root(); root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.live2d-', dir=root))
    try:
        path = temporary / NAME
        path.write_bytes(data)
        validate(path)
        (temporary / 'LICENSE.Live2D.md').write_bytes(notice)
        (temporary / 'origin.json').write_text(json.dumps({'sha256':digest,'sdk':archive_path.name,'download_url':DOWNLOAD_URL}) + '\n')
        destination = root / digest
        if not destination.exists():
            temporary.rename(destination)
        elif hashlib.sha256((destination / NAME).read_bytes()).hexdigest() != digest:
            raise ValueError('Cached Live2D Core has changed; remove the damaged dependency cache and import the SDK again.')
        (root / 'selected.json').write_text(json.dumps({'sha256':digest}) + '\n')
        return validate(destination / NAME)
    finally:
        if temporary.exists():
            if not temporary.resolve().is_relative_to(root.resolve()):
                raise ValueError('Live2D temporary cache escaped its intended directory.')
            shutil.rmtree(temporary)


def find_core(*roots: Path) -> Path | None:
    for root in roots:
        for relative in ('lib/py3-linux-aarch64/' + NAME, 'py3-linux-aarch64/' + NAME, NAME):
            path = root / relative
            if path.is_file():return validate(path)
    try:
        record = json.loads((cache_root() / 'selected.json').read_text())
        digest = record['sha256']
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Invalid Core cache record')
        path = cache_root() / digest / NAME
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:raise ValueError('Core cache checksum mismatch')
        return validate(path)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    for archive in sorted((Path.home() / 'Downloads').glob('CubismSdkForNative-*.zip'), reverse=True):
        try:return import_sdk(archive)
        except (OSError,ValueError,zipfile.BadZipFile):continue
    return None


def install(core: Path, output: Path) -> None:
    target = output / 'lib/py3-linux-aarch64' / NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(validate(core), target)
    notice = core.parent / 'LICENSE.Live2D.md'
    if notice.is_file():shutil.copyfile(notice, output / 'LICENSE.Live2D.md')
    (output / 'LIVE2D-RUNTIME.json').write_text(json.dumps({
        'architecture':'aarch64','library':'lib/py3-linux-aarch64/' + NAME,
        'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'provider':'User-supplied Cubism SDK for Native', 'license_url':DOWNLOAD_URL,
    },indent=2) + '\n')
