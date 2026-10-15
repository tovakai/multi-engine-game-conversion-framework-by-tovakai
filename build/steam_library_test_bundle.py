"""Prepare/run pure-Python fixture tests on Frame without installing dependencies.

Usage on Windows: python build/steam_library_test_bundle.py prepare
Usage on Frame: python3 /tmp/steam_library_test_bundle.py run /tmp/steam-library-tests.zip
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def prepare():
    root = Path(__file__).resolve().parents[1]
    site = root / '.venv/Lib/site-packages'
    archive = root / 'build/steam-library-tests.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as out:
        out.write(site / 'py.py', 'dependencies/py.py')
        out.write(site / 'pefile.py', 'dependencies/pefile.py')
        for package in ['pytest', '_pytest', 'pluggy', 'packaging', 'iniconfig', 'pygments', 'ordlookup']:
            for path in (site / package).rglob('*.py'):
                out.write(path, 'dependencies/' + path.relative_to(site).as_posix())
        for package in ['megcfbt', 'renframe', 'rpgmframe', 'gamemakerframe', 'loveframe',
                        'agsframe', 'constructframe', 'monoframe', 'celesteframe', 'unityframe']:
            for path in (root / package).rglob('*'):
                if path.is_file() and path.suffix in {'.py', '.json'}:
                    out.write(path, path.relative_to(root).as_posix())
        for path in (root / 'megcfbt/runtime_support').rglob('*'):
            if path.is_file() and path.suffix != '.json':
                out.write(path, path.relative_to(root).as_posix())
        for name in ['test_asset_dedup.py', 'test_steam_library.py', 'test_frame_package.py',
                     'test_router_steam_metadata.py', 'test_native_backends.py', 'test_monoframe.py',
                     'test_celesteframe.py', 'test_easyrpg_backend.py',
                     'test_steam_client.py', 'test_steam_live_link.py', 'test_steam_native_chain.py']:
            out.write(root / 'tests' / name, 'tests/' + name)
    print(archive)


def run(archive):
    with tempfile.TemporaryDirectory(prefix='megcfbt-library-pytest-') as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive) as packed:
            packed.extractall(root)
        home = root / 'synthetic-home'
        home.mkdir()
        env = dict(os.environ, HOME=str(home), PYTHONPATH=str(root / 'dependencies') + os.pathsep + str(root))
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--tb=short', '-p', 'no:cacheprovider',
                                 '--basetemp', str(root / 'fixtures'),
                                 'tests/test_asset_dedup.py', 'tests/test_steam_library.py',
                                 'tests/test_frame_package.py', 'tests/test_router_steam_metadata.py',
                                 'tests/test_steam_client.py', 'tests/test_steam_live_link.py',
                                 'tests/test_steam_native_chain.py'], cwd=root, env=env)
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    else:
        run(Path(sys.argv[2]))
