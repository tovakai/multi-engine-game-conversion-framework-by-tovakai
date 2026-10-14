"""Prevent runtime rebuild instructions from depending on missing local helpers."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_untilthen_rebuild_local_imports_have_bundled_sources():
    index = json.loads((ROOT / 'rpgmframe/godot_extension_runtime_index.json').read_text(encoding='utf-8'))
    files = index['recipes']['godot-4.1.4-until-then-native-arm64-v1']['archive_files']
    script = ROOT / 'experiments/until-then/build_public_extensions.py'
    imports = {node.module for node in ast.walk(ast.parse(script.read_text(encoding='utf-8-sig')))
               if isinstance(node, ast.ImportFrom) and node.module == 'steam_sdk_compat'}
    assert imports == {'steam_sdk_compat'}
    assert 'sources/steam_sdk_compat.py' in files
    assert (script.parent / 'steam_sdk_compat.py').is_file()
    assert 'licenses/LICENSE-GameNetworkingSockets.txt' in files
