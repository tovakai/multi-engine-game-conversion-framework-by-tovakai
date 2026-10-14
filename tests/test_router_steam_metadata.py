"""Production inspection/build/router/ZIP/installer regression, synthetic games only.

Managed host preparers and licensed FMOD validation are substituted; real source
hash gates, backend builders, runtime validation, router and packaging execute.
"""
import hashlib
import importlib.util
import json
import subprocess
import sys
import types
import zipfile
from pathlib import Path

import pytest

from megcfbt import router
from megcfbt.frame_package import load_frame_metadata
from test_native_backends import gm_data, elf
import test_monoframe as mono_fixtures
import test_celesteframe as celeste_fixtures


def host_preparer(monkeypatch, backend, prepare):
    substitute = types.SimpleNamespace(**vars(subprocess))
    substitute.run = prepare
    monkeypatch.setattr(backend, 'subprocess', substitute)


def fixture_game(tmp_path, monkeypatch, backend, trusted=True):
    monkeypatch.setattr(router, 'complete_frame_artwork', lambda *a, **kw: None)
    if backend == 'monoframe':
        source = mono_fixtures.game(tmp_path, monkeypatch)
        runtime = mono_fixtures.sdk(tmp_path)
        def prepare(command, **kwargs):
            target = Path(command[command.index('--game-dir') + 1])
            (target / 'Stardew Valley.dll').write_bytes(b'prepared synthetic managed assembly')
            (target / 'Content/Maps/patched.xnb').write_bytes(b'XNBprepared resource')
            return subprocess.CompletedProcess(command, 0, 'Prepared')
        host_preparer(monkeypatch, mono_fixtures.backend, prepare)
        return source, runtime, {}
    if backend == 'celesteframe':
        source = celeste_fixtures.source(tmp_path, monkeypatch)
        runtime = celeste_fixtures.sdk(tmp_path)
        fmod = tmp_path / 'owner-fmod.tar.gz'
        import io, tarfile
        with tarfile.open(fmod, 'w:gz') as archive:
            for component, name in [('core', 'fmod'), ('studio', 'fmodstudio')]:
                data = celeste_fixtures.elf()
                member = tarfile.TarInfo(f'fmodstudioapi20315linux/api/{component}/lib/arm64/lib{name}.so.14.15')
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        monkeypatch.setattr(celeste_fixtures.backend, 'validate_fmod_sdk', lambda p: p)
        monkeypatch.setattr(celeste_fixtures.runtime, 'validate_fmod_sdk', lambda p: p)
        def prepare(command, **kwargs):
            Path(command[-1]).write_bytes(b'prepared synthetic Celeste assembly')
            (Path(command[-1]).parent / 'Content/Maps/patched.xnb').write_bytes(b'XNBprepared resource')
            return subprocess.CompletedProcess(command, 0, 'Prepared')
        host_preparer(monkeypatch, celeste_fixtures.backend, prepare)
        return source, runtime, {'celeste_sdk': fmod}
    source = tmp_path / 'Steam/steamapps/common/Exact source game'
    source.mkdir(parents=True)
    if trusted:
        (source.parents[1] / 'appmanifest_123456.acf').write_text(
            '"AppState" { "appid" "123456" "installdir" "Exact source game" }')
    else:
        # A sidecar can request runtime initialization, but cannot prove identity.
        (source / 'steam_appid.txt').write_text('123456')
    runtime = tmp_path / 'sdk'
    runtime.mkdir()
    if backend == 'gamemakerframe':
        gm_data(source / 'data.win')
        executable = 'butterscotch'
    elif backend == 'loveframe':
        (source / 'main.lua').write_text('function love.draw() end')
        (source / 'conf.lua').write_text('function love.conf(t) t.version="11.4" end')
        executable = 'love'
    elif backend == 'rpgmframe':
        from test_easyrpg_backend import game
        game(source / 'original')
        executable = 'easyrpg-player'
    else:
        (source / 'Game.ags').write_bytes(b'CLIB\x1a synthetic game data')
        executable = 'ags'
    elf(runtime / executable)
    return source, runtime, {}


def convert(tmp_path, monkeypatch, backend, trusted=True):
    source, runtime, options = fixture_game(tmp_path, monkeypatch, backend, trusted)
    if backend in {'monoframe', 'celesteframe'}:
        content = source / 'Content/Maps'
        content.mkdir(parents=True, exist_ok=True)
        (content / 'unchanged.xnb').write_bytes(b'XNBunchanged source asset')
        (content / 'patched.xnb').write_bytes(b'XNBsource resource')
    before = {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.rglob('*') if p.is_file()}
    inspection = router.inspect_source(source)
    canonical_backend = 'monoframe' if backend == 'celesteframe' else backend
    assert inspection.buildable and inspection.backend == canonical_backend
    # Observe the real backend's metadata just before the router enriches it.
    original_write = router.write_frame_metadata
    emitted = []
    launchers = []
    def observe(root, **kwargs):
        emitted.append(load_frame_metadata(root) if (root / '.megcfbt/package.json').exists() else {})
        launchers.append((root / 'launch.sh').read_bytes())
        return original_write(root, **kwargs)
    monkeypatch.setattr(router, 'write_frame_metadata', observe)
    result = router.build_source(source, output=tmp_path / 'converted-frame',
                                 backend_runtime=runtime, archive=True, **options)
    assert before == {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in source.rglob('*') if p.is_file()}
    extracted = tmp_path / 'extracted'
    with zipfile.ZipFile(result.archive_path) as archive:
        archive.extractall(extracted)
    root = next(extracted.iterdir())
    metas = [json.loads((base / '.megcfbt/package.json').read_text(encoding='utf-8'))
             for base in (root, root / 'payload')]
    # Execute the exact identity/capability code shipped inside the extracted ZIP.
    module_path = root / '.megcfbt/steam_library.py'
    package = types.ModuleType('extracted_package')
    package.__path__ = [str(module_path.parent)]
    monkeypatch.setitem(sys.modules, 'extracted_package', package)
    monkeypatch.delitem(sys.modules, 'extracted_package.asset_dedup', raising=False)
    spec = importlib.util.spec_from_file_location('extracted_package.steam_library', module_path)
    installer = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, installer)
    spec.loader.exec_module(installer)
    for meta in metas:
        assert meta['engine'] == inspection.engine
        assert meta['backend'] == canonical_backend
        for key in ('steam_identity', 'steam_runtime_appid', 'compatibility_profile',
                    'runtime_engine_version', 'game_version', 'conversion'):
            if not emitted[0] and key == 'conversion':
                assert meta['conversion']['converter']['version'].startswith('0.1.1.0')
                continue
            expected = emitted[0].get(key)
            if backend == 'celesteframe' and key == 'runtime_engine_version':
                expected = 'FNA 23.10 / .NET 8.0.31'
            if backend == 'celesteframe' and key == 'game_version':
                expected = '1.4.0.0'
            assert meta.get(key) == expected, key
        assert meta['architecture'] == 'aarch64'
        assert meta['target_platform'] == 'linux-aarch64'
    assert (root / 'payload/launch.sh').read_bytes() == launchers[0]
    return root, metas, installer


@pytest.mark.parametrize('backend,number', [('celesteframe', 504230), ('monoframe', 413150),
    ('gamemakerframe', 123456), ('loveframe', 123456), ('agsframe', 123456)])
def test_full_pipeline_keeps_installer_identity(tmp_path, monkeypatch, backend, number):
    root, metas, installer = convert(tmp_path, monkeypatch, backend)
    for meta in metas:
        assert installer.identity(meta) == number
        assert installer.capability(meta)[0]
        if backend in {'celesteframe', 'monoframe'}:
            assert meta.get('steam_identity') is None  # Audited hash profile alone suffices.
            inventory = installer.assets().origins(root / 'payload', meta)
            assert inventory['Content/Maps/unchanged.xnb']['status'] == 'unchanged'
            assert inventory['Content/Maps/patched.xnb']['status'] == 'modified'
        else:
            assert meta['steam_identity']['source'] == 'installed-source-manifest'
            assert int(meta['steam_identity']['appid']) == number
    assert (root / 'payload/steam_appid.txt').read_text().strip() == str(number)


@pytest.mark.parametrize('backend', ['gamemakerframe', 'loveframe', 'agsframe'])
def test_untrusted_sidecar_survives_only_as_runtime_hint(tmp_path, monkeypatch, backend, capsys):
    root, metas, installer = convert(tmp_path, monkeypatch, backend, trusted=False)
    for meta in metas:
        assert meta.get('steam_identity') is None
        assert installer.identity(meta) is None
    monkeypatch.setattr(installer, 'choose', lambda prompt: '1')
    assert installer.menu(root, metas[0]['name'], root / 'launch.sh') is True
    assert 'no trustworthy original Steam AppID' in capsys.readouterr().out


@pytest.mark.parametrize('change', ['identity-conflict', 'runtime-conflict', 'unsupported',
                                  'backend-conflict', 'invalid-appid', 'unverified-identity'])
def test_extracted_pipeline_fails_safely_with_nonsteam_choice(tmp_path, monkeypatch, capsys, change):
    root, metas, installer = convert(tmp_path, monkeypatch, 'monoframe')
    meta = metas[0]
    if change == 'identity-conflict':
        meta['steam_identity'] = {'source': 'installed-source-manifest', 'appid': 504230}
    elif change == 'runtime-conflict':
        meta['steam_runtime_appid'] = 504230
    elif change == 'unsupported':
        meta['backend'] = 'unityframe'
    elif change == 'invalid-appid':
        meta['steam_runtime_appid'] = True
    elif change == 'unverified-identity':
        meta['steam_identity'] = {'source': 'title-match', 'appid': 413150}
    else:
        meta['engine'] = 'CelesteFrame'
    (root / '.megcfbt/package.json').write_text(json.dumps(meta))
    monkeypatch.setattr(installer, 'choose', lambda prompt: '1')
    assert installer.menu(root, meta['name'], root / 'launch.sh') is True
    assert 'Automatic linking unavailable' in capsys.readouterr().out


def test_conflicting_source_manifest_is_not_packaged(tmp_path, monkeypatch):
    source, runtime, options = fixture_game(tmp_path, monkeypatch, 'gamemakerframe')
    (source.parents[1] / 'appmanifest_999.acf').write_text(
        '"AppState" { "appid" "999" "installdir" "Exact source game" }')
    with pytest.raises(router.ConversionError, match='[Cc]onflict'):
        router.build_source(source, output=tmp_path / 'converted', backend_runtime=runtime)
    assert not list(tmp_path.glob('*.zip'))


def test_unsupported_backend_full_pipeline_offers_nonsteam(tmp_path, monkeypatch, capsys):
    root, metas, installer = convert(tmp_path, monkeypatch, 'rpgmframe')
    for meta in metas:
        assert not installer.capability(meta)[0]
        assert installer.identity(meta) == 123456  # Evidence does not authorize a backend.
    monkeypatch.setattr(installer, 'choose', lambda prompt: '1')
    assert installer.menu(root, metas[0]['name'], root / 'launch.sh') is True
    assert 'Automatic linking unavailable' in capsys.readouterr().out
