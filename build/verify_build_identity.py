"""Verify the frozen GUI/CLI receipt against distributable provenance and checksums."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from megcfbt.version import display_version


def verify(application, receipt, target):
    build = json.loads((application / 'BUILD.json').read_text(encoding='utf-8'))
    frozen = json.loads(receipt.read_text(encoding='utf-8'))
    assert frozen['state'] == 'complete' and frozen['frozen'], 'Missing frozen startup verification'
    identity = {key: value for key, value in build.items() if key != 'app_name'}
    assert frozen['build_info'] == identity == frozen['cli_build_info'], 'Frozen GUI/CLI identity mismatch'
    assert frozen['version'] == build['version'], 'Application version mismatch'
    assert frozen['version_display'] == display_version(identity), 'GUI version mismatch'
    assert build['platform'] == target, 'Build target mismatch'
    assert build['architecture'] == {'windows-x64': 'x86_64', 'linux-aarch64': 'aarch64'}[target]
    checksum = ROOT / 'dist' / f'SHA256SUMS-{target}.txt'
    digest, filename = checksum.read_text().strip().split('  ', 1)
    assert f"-{build['version']}-{target}." in filename, 'Archive version mismatch'
    actual = hashlib.sha256()
    with (checksum.parent / filename).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            actual.update(chunk)
    assert actual.hexdigest() == digest, 'Archive checksum mismatch'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--platform', choices=['windows-x64', 'linux-aarch64'], required=True)
    args = parser.parse_args()
    verify(args.application, args.receipt, args.platform)
