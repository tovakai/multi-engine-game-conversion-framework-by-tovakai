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
        for package in ['pytest', '_pytest', 'pluggy', 'packaging', 'iniconfig', 'pygments']:
            for path in (site / package).rglob('*.py'):
                out.write(path, 'dependencies/' + path.relative_to(site).as_posix())
        for path in (root / 'megcfbt').glob('*.py'):
            out.write(path, path.relative_to(root).as_posix())
        for name in ['test_asset_dedup.py', 'test_steam_library.py', 'test_frame_package.py']:
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
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                                 '--basetemp', str(root / 'fixtures'), 'tests'], cwd=root, env=env)
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    else:
        run(Path(sys.argv[2]))
