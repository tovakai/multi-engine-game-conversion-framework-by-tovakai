import json
from pathlib import Path
import shutil
import struct
import subprocess
import zipfile

import pytest

from megcfbt.router import build_source, inspect_source
from rpgmframe.mkxp_backend import _migration_preloads


def test_router_packages_rgss_input_compat_without_changing_source(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    original = b'RGSSAD\x00\x03' + b'synthetic encrypted assets'
    (source / 'Game.rgss3a').write_bytes(original)
    (source / 'Game.ini').write_text('[Game]\nLibrary=System/RGSS301.dll\nScripts=Data/Scripts.rvdata2\nTitle=Test RGSS\n', encoding='utf-8')
    runtime = tmp_path / 'runtime'
    preloads = runtime / 'scripts/preload'
    preloads.mkdir(parents=True)
    header = bytearray(64)
    header[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<H', header, 18, 183)
    (runtime / 'mkxp-z.aarch64').write_bytes(header)
    for name in ('ruby_classic_wrap.rb', 'mkxp_wrap.rb', 'win32_wrap.rb'):
        (preloads / name).write_text('# synthetic runtime preload\n', encoding='utf-8')
    assert inspect_source(source).backend == 'rpgmframe'
    result = build_source(source, output=tmp_path / 'converted', backend_runtime=runtime)
    archives = list(tmp_path.glob('*.zip'))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as archive:
        names = archive.namelist()
        config_name = next(name for name in names if name.endswith('/game/mkxp.json'))
        config = json.loads(archive.read(config_name))
        assert config['preloadScript'][-2:] == ['../scripts/preload/win32_wrap.rb', '../scripts/preload/megcfbt_rgss_input.rb']
        compat = next(name for name in names if name.endswith('/scripts/preload/megcfbt_rgss_input.rb'))
        assert archive.read(compat) == (Path(__file__).parents[1] / 'rpgmframe/runtime_support/rgss_input_compat.rb').read_bytes()
        game = next(name for name in names if name.endswith('/game/Game.rgss3a'))
        assert archive.read(game) == original
    assert (source / 'Game.rgss3a').read_bytes() == original
    assert sorted(path.name for path in source.iterdir()) == ['Game.ini', 'Game.rgss3a']


def test_compat_not_enabled_without_win32_wrapper(tmp_path):
    assert '../scripts/preload/megcfbt_rgss_input.rb' not in _migration_preloads(tmp_path, tmp_path, None, [])


def test_existing_preloads_remain_ordered_and_unique(tmp_path):
    preload = tmp_path / 'scripts/preload'
    preload.mkdir(parents=True)
    (preload / 'win32_wrap.rb').write_text('# wrapper', encoding='utf-8')
    existing = ['custom.rb', 'custom.rb', '../scripts/preload/win32_wrap.rb']
    assert _migration_preloads(tmp_path, tmp_path, None, existing) == [
        'custom.rb', '../scripts/preload/win32_wrap.rb', '../scripts/preload/megcfbt_rgss_input.rb']


def test_rgss_input_ruby_contract():
    ruby = shutil.which('ruby')
    if ruby is None:
        pytest.skip('Ruby unavailable; fixture also runs through mkxp-z on Frame')
    root = Path(__file__).parents[1]
    result = subprocess.run([ruby, str(root / 'tests/fixtures/rgss_input_compat.rb'), str(root / 'rpgmframe/runtime_support/rgss_input_compat.rb')], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'RGSS_INPUT_COMPAT_PASS' in result.stdout
