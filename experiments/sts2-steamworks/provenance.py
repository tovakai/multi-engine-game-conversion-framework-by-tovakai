"""Build identity for source, frozen and standalone STS2 tools."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys


def build_identity():
    # Standalone tools carry the identity of the bundled code, not a device install.
    embedded = Path(__file__).with_name('_build_info.json')
    if embedded.is_file():
        return json.loads(embedded.read_text(encoding='utf-8'))
    source = Path(__file__).resolve().parents[2]
    if (source / 'megcfbt/version.py').is_file() and str(source) not in sys.path:
        sys.path.insert(0, str(source))
    try:
        from megcfbt.version import get_build_info
        return get_build_info()
    except ImportError:
        return {'version': None, 'commit': None, 'short_commit': None,
                'build_kind': 'unknown', 'tracked_changes': None,
                'metadata_status': 'Bundled converter build metadata unavailable'}


def conversion_identity():
    return {'converter': build_identity(),
            'converted_utc': datetime.now(timezone.utc).isoformat(),
            'execution_architecture': platform.machine(), 'target_platform': 'linux-aarch64',
            'engine': 'godot', 'engine_version': '4.5.1',
            'runtime_engine_version': '4.5.1'}


def bundled_identity_bytes():
    return (json.dumps(build_identity(), indent=2) + '\n').encode('utf-8')
