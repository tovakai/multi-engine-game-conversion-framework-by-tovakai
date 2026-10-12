"""Prepare a private STS2 transfer ZIP; complete native compilation on the Frame."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from converter_io import safe, relative, write_new, publish_new
from convert_sts2 import convert, load_profile, executable
from preflight import inspect_source
from sdk_archive import prepare_sdk
from build_native import sdk_headers
from fetch_converter_runtimes import fetch
from verify_output import inspect
from package_converter import FILES
from frame_install import KIND, HANDOFF
import retail_107  # Available in-process in frozen Windows builds too.
from provenance import build_identity, conversion_identity, bundled_identity_bytes

INSTALL = b'''#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.11 or newer is required on the Frame." >&2
    exit 2
fi
exec python3 -B "$ROOT/backend/frame_install.py" "$ROOT" "$@"
'''

INSTRUCTIONS = '''Slay the Spire 2: finish installation on the Steam Frame

This package is prepared, but is not yet playable.
1. Install Slay the Spire 2 through Steam on the Frame and let its download/update
   finish. The original Steam entry is needed for launch; a non-Steam shortcut is
   not sufficient. The installer checks this before any compilation.
2. Copy the ZIP to writable Frame storage with at least 10 GiB free AFTER extraction.
3. Extract the ZIP and keep the entire folder together.
4. Open a terminal in this extracted folder and run: sh ./install.sh
5. Wait for native compilation and verification. The terminal shows an animated
   activity bar, elapsed time, the current component and live build messages.
   This is activity reporting, not an estimated completion percentage.
   First installation needs internet
   access to download pinned extension sources and the private compiler tool.
6. Accept the installer prompt to configure the existing STS2 Steam launch option
   directly. It backs up the previous setting; no text needs to be copied into VR.
   Steam must be running with its local library UI endpoint available.
7. Press Play through that Steam entry. To restore: sh ./install.sh --restore-steam
   To connect an already compiled game: sh ./install.sh --connect-steam

Frame prerequisites: Linux ARM64, Python 3.11+ with venv, Git, g++, readelf,
the supported installed Valve ARM64 Steam API and Steam host runtime.
The installer uses private build tools; it does not install system packages.
Steam settings change only after you accept the prompt or use --connect-steam.
Build logs and verified cache are retained for retries.
If installation stops, resolve the reported error and rerun the same script.

Windows has already verified the originals, adapted managed code and the pack,
and downloaded/extracted the pinned Godot/.NET/Sentry runtimes. The Frame builds
Spine and FMOD extensions and supplies its installed Valve API, then verifies
the complete game. Windows originals remain untouched.

This private package contains your game and selected FMOD SDK material.
Do not redistribute it. Obtain FMOD yourself from
https://www.fmod.com/download#fmodengine under the applicable vendor terms.
The converter supplies no FMOD SDK. Preserve applicable game/middleware permissions.
STS2 remains experimental; integrity verification does not establish gameplay,
save/Cloud or achievement compatibility.
'''


def prepare(source, output, *, sdk, cache, archive=True, progress=None, stage=None):
    progress = progress or (lambda message: None)
    stage = stage or (lambda value, message: None)
    source, output, sdk, cache = map(safe, (source, output, sdk, cache))
    if output.exists():
        raise ValueError('Transfer folder already exists; choose a new output folder.')
    for path in (source, sdk, cache):
        if output == path or path in output.parents or output in path.parents:
            raise ValueError('Transfer output must be separate from inputs and cache.')
    version = build_identity().get('version') or 'unknown'
    archive_path = output.with_name(output.name + '-prep-conv-v' + version + '-linux-aarch64.zip') if archive else None
    if archive_path is not None and archive_path.exists():
        raise ValueError('Transfer ZIP already exists; choose a new output folder.')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage(.08, 'Verifying the supported original game')
    report = inspect_source(source)
    if report['errors']:
        raise ValueError('Unsupported or altered original game: ' + str(report['errors']))
    if not sdk.is_file():
        raise ValueError('Select the original FMOD 2.03.15 Linux SDK archive, not an extracted folder.')
    profile = load_profile(source)
    temporary = Path(tempfile.mkdtemp(prefix='.sts2-handoff-', dir=output.parent))
    zip_temp = None
    try:
        stage(.18, 'Verifying and preparing your FMOD SDK')
        vendor = prepare_sdk(sdk, temporary / 'vendor-sdk')
        sdk_headers(vendor)
        stage(.28, 'Downloading verified Godot, .NET and Sentry runtimes')
        progress('Downloading verified public runtimes; first preparation requires internet access.')
        archives = fetch(cache / 'runtimes')
        stage(.48, 'Preparing managed code, game pack and ARM64 runtimes')
        convert(source, temporary / 'prepared', None, archives, _profile=profile, _defer_native=True)
        stage(.78, 'Adding the Frame installer')
        here = Path(__file__).resolve().parent
        for name in FILES:
            target = temporary / 'backend' / relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(here / relative(name), target)
        license_path = here / 'LICENSE'
        if not license_path.exists():
            license_path = here.parents[1] / 'LICENSE'
        shutil.copyfile(license_path, temporary / 'backend/LICENSE')
        write_new(temporary / 'backend/_build_info.json', bundled_identity_bytes())
        write_new(temporary / 'install.sh', INSTALL, 0o755)
        write_new(temporary / 'INSTALL-ON-FRAME.txt', INSTRUCTIONS.encode())
        files = [{'path': path.relative_to(temporary).as_posix(), **inspect(path)}
                 for path in sorted(temporary.rglob('*')) if path.is_file()]
        handoff = {'kind': KIND, 'release': profile['release'], 'commit': profile['commit'],
                   'preparation': conversion_identity(),
                   'files': files, 'source_validation': report,
                   'scope': 'Prepared transfer package; native installation on the Frame is required.'}
        write_new(temporary / HANDOFF, (json.dumps(handoff, indent=2, sort_keys=True) + '\n').encode())
        if archive_path is not None:
            stage(.86, 'Creating the Frame transfer ZIP')
            fd, name = tempfile.mkstemp(prefix='.sts2-handoff-', suffix='.zip', dir=output.parent)
            os.close(fd)
            zip_temp = Path(name)
            with zipfile.ZipFile(zip_temp, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as package:
                for path in sorted(temporary.rglob('*')):
                    if not path.is_file():
                        continue
                    name = path.relative_to(temporary).as_posix()
                    info = zipfile.ZipInfo(output.name + '/' + name)
                    info.create_system = 3
                    mode = 0o755 if name == 'install.sh' or (name.startswith('prepared/') and executable(name[9:])) else 0o644
                    info.external_attr = (0o100000 | mode) << 16
                    with path.open('rb') as source_stream, package.open(info, 'w', force_zip64=True) as dest:
                        shutil.copyfileobj(source_stream, dest, 1024 * 1024)
            publish_new(zip_temp, archive_path)
            zip_temp = None
        publish_new(temporary, output)
        temporary = None
        stage(1., 'Transfer package ready; finish installation on the Frame')
        return {'output': str(output), 'archive': str(archive_path) if archive_path else None,
                'limitations': ['Prepared package: transfer to the Frame and run sh ./install.sh before playing.']}
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)
        if zip_temp is not None:
            zip_temp.unlink(missing_ok=True)
