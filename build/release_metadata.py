"""Create versioned application archives with source provenance and notices."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tarfile
import os
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from megcfbt import APP_NAME
from megcfbt.version import RELEASE_VERSION, resolve_source, validate_release


def package(application: Path, platform: str) -> Path:
    application = application.resolve()
    metadata_path = application / '_internal/megcfbt/_build_info.json'
    if not metadata_path.is_file():
        metadata_path = application / 'megcfbt/_build_info.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    source = resolve_source(ROOT)
    for key in ('schema', 'release_version', 'version', 'commit', 'tracked_changes', 'tracked_diff_sha256', 'build_kind'):
        if metadata.get(key) != source.get(key):
            raise ValueError(f'Frozen application and source identity disagree: {key}')
    if metadata.get('platform') != platform:
        raise ValueError('Frozen application platform disagrees with archive target')
    if os.environ.get('GITHUB_REF_TYPE') == 'tag':
        validate_release(os.environ['GITHUB_REF_NAME'], metadata)
    version = metadata['version']
    binary = application / (APP_NAME + ('.exe' if platform == 'windows-x64' else ''))
    with binary.open('rb') as stream:
        header = stream.read(64)
        if platform == 'windows-x64':
            if header[:2] != b'MZ':
                raise ValueError('Windows application is not a PE executable')
            stream.seek(struct.unpack_from('<I', header, 60)[0])
            signature = stream.read(6)
            valid = signature[:4] == b'PE\0\0' and struct.unpack_from('<H', signature, 4)[0] == 0x8664
        else:
            valid = header[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', header, 18)[0] == 183
        if not valid:
            raise ValueError(f'Application architecture does not match {platform}')
    commit = metadata['commit']
    dirty = metadata['tracked_changes']
    metadata = {**metadata, 'app_name': APP_NAME}
    (application / 'BUILD.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    (application / 'BUILD.txt').write_text(f'version={version}\ncommit={commit}\nplatform={platform}\ntracked_changes={dirty}\n', encoding='utf-8')
    for source in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / source, application / source)
    notes_path = ROOT / f'docs/releases/{RELEASE_VERSION}.md'
    if not notes_path.is_file() and RELEASE_VERSION.endswith('.0'):
        notes_path = ROOT / f'docs/releases/{RELEASE_VERSION[:-2]}.md'
    if metadata['build_kind'] == 'release':
        notes = notes_path.read_text(encoding='utf-8')
    else:
        notes = 'Development build; not a public release. See BUILD.json for exact source identity.\n'
    documentation = f'https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/blob/{commit}/docs/'
    (application / 'RELEASE-NOTES.md').write_text(notes.replace('](../', '](' + documentation), encoding='utf-8')
    (application / 'README.txt').write_text(
        f'{APP_NAME} {version}\n\nRun {binary.name}.\n'
        'Drop a supported game folder or ZIP, inspect the result, and press Convert.\n'
        'Supported runtimes download, verify and cache automatically.\n'
        'Transfer and extract the generated game ZIP on Frame; run install-to-steam.sh.\n'
        'Launch through Steam for Steam Input controller mapping.\n'
        'See RELEASE-NOTES.md for supported scope and experimental limitations.\n'
        'SDK prerequisites such as Live2D and FMOD must be supplied by the user.\n'
        'No game assets or proprietary vendor SDKs are included in this application.\n', encoding='utf-8')
    suffix = 'zip' if platform == 'windows-x64' else 'tar.gz'
    archive = ROOT / 'dist' / f'multi-engine-game-conversion-framework-by-tovakai-{version}-{platform}.{suffix}'
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_name(archive.name + '.tmp')
    if platform == 'windows-x64':
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for file in sorted(application.rglob('*')):
                if file.is_file():
                    output.write(file, Path(application.name) / file.relative_to(application))
        with zipfile.ZipFile(temporary) as check:
            if check.testzip() is not None:
                raise ValueError('Application archive integrity check failed')
    else:
        with tarfile.open(temporary, 'w:gz') as output:
            output.add(application, arcname=application.name)
        with tarfile.open(temporary, 'r:gz') as check:
            for member in check:
                if member.isfile():
                    with check.extractfile(member) as stream:
                        while stream.read(1 << 20):
                            pass
    temporary.replace(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (archive.parent / f'SHA256SUMS-{platform}.txt').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    print(archive)
    print(digest)
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application', type=Path, required=True)
    parser.add_argument('--platform', choices=['windows-x64', 'linux-aarch64'], required=True)
    args = parser.parse_args()
    package(args.application, args.platform)
