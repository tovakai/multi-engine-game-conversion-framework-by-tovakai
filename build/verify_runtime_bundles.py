"""Check optional offline runtime archives before embedding in an application."""
from pathlib import Path
import hashlib
import json
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rpgmframe.godot_extension_runtime import recipe_entry, REQUIRED


def verify(archive: Path):
    entry = recipe_entry()
    if entry is None or archive.name != entry['archive_name']:
        raise ValueError('No allowlisted recipe for embedded runtime archive')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Embedded runtime SHA-256 mismatch')
    seen = set()
    with tarfile.open(archive) as tar:
        for member in tar:
            if not member.isfile() or member.name not in entry['archive_files'] or member.name in seen:
                raise ValueError('Unexpected embedded runtime archive member')
            seen.add(member.name)
            with tar.extractfile(member) as stream:
                data = stream.read()
            if member.name != 'runtime.json' and hashlib.sha256(data).hexdigest() != entry['files'][member.name]:
                raise ValueError('Embedded runtime member integrity failure')
            if member.name == 'runtime.json':
                if json.loads(data)['files'] != entry['files']:
                    raise ValueError('Embedded runtime manifest disagrees with pinned index')
            if member.name in REQUIRED and (data[:6] != b'\x7fELF\x02\x01'
                    or len(data) < 20 or int.from_bytes(data[18:20], 'little') != 183):
                raise ValueError('Embedded runtime binary is not Linux AArch64')
    if seen != set(entry['archive_files']):
        raise ValueError('Incomplete embedded runtime archive')
    print('VERIFIED_OFFLINE_RUNTIME', archive.name, flush=True)


if __name__ == '__main__':
    for argument in sys.argv[1:]:
        verify(Path(argument))
