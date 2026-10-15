"""Opt-in synthetic SD-card benchmark; never uses real Steam game files."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


directory = Path(sys.argv[1]).resolve()
if not directory.is_mount():
    raise ValueError('Benchmark requires an explicitly mounted storage directory')
sys.path.insert(0, '/tmp')
lib = load('benchmark_steam_library', Path('/tmp/benchmark_steam_library.py'))
results = []
with tempfile.TemporaryDirectory(prefix='megcfbt-dedup-speed-', dir=directory) as temporary:
    for label, module_path in [('previous', '/tmp/benchmark_asset_original.py'),
                               ('optimized', '/tmp/benchmark_asset_current.py')]:
        module = load('benchmark_' + label, Path(module_path))
        original = Path(temporary) / label / 'synthetic-original'
        package = Path(temporary) / label / 'synthetic-converted'
        (original / 'Content/Maps').mkdir(parents=True)
        (package / 'game/Content/Maps').mkdir(parents=True)
        (package / '.megcfbt').mkdir()
        (package / 'launch.sh').write_text('#!/bin/sh\nexit 0\n')
        payload = b'XNB' + b'synthetic read-only asset' * 100
        for index in range(128):
            for content in (original / 'Content/Maps', package / 'game/Content/Maps'):
                (content / f'{index:03}.xnb').write_bytes(payload)
        meta = {'engine': 'CelesteFrame', 'architecture': 'aarch64', 'target_platform': 'linux-aarch64',
                'compatibility_profile': 'celeste-steam-xna-1.4.0.0', 'launcher': 'launch.sh',
                'conversion': {'converter': {'version': 'benchmark-synthetic'}}}
        detected = {'state': 'installed', 'installations': [{'game': str(original)}]}
        module.library = lambda: lib
        lib.installation = lambda number: detected
        lib.assets = lambda: module
        module.probe_isolation = lambda package: '/usr/bin/bwrap'
        full_saves = []
        save = module.save
        def tracked(root, data):
            save(root, data)
            full_saves.append(module.manifest_path(root).stat().st_size)
        module.save = tracked
        start = time.monotonic()
        result = module.enable(package, meta, detected, experimental=True)
        elapsed = time.monotonic() - start
        assert result['linked'] == 128
        results.append({'implementation': label, 'files': 128, 'seconds': round(elapsed, 3),
                        'full_checkpoints': len(full_saves), 'full_checkpoint_bytes': sum(full_saves)})
        module.restore_assets(package, detected)
print(json.dumps({'storage': str(directory), 'synthetic_only': True, 'results': results}, indent=2))
