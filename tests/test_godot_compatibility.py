from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import zipfile

import pytest

from rpgmframe.godot import GodotPack
from rpgmframe.godot_compatibility import (
    CASSETTE_PROFILE_ID, CASSETTE_RUNTIME_ID, cassette_rendering_profile,
    install_cassette_rendering_profile, merge_depth_override,
)
from rpgmframe.launchers import godot_launcher_body


def pack():
    return GodotPack(Path("CassetteBeasts.pck"), 0, 100, 1, 3, 5, 1, False)


def runtime():
    return {"recipe_id": CASSETTE_RUNTIME_ID, "engine_version": "3.5.1", "pack_loading": "main-pack"}


@pytest.mark.parametrize("changed_pack,app_id,metadata", [
    (replace(pack(), path=Path("Other.pck")), "1321440", runtime()),
    (replace(pack(), minor=6), "1321440", runtime()),
    (pack(), "1942280", runtime()),
    (pack(), None, runtime()),
    (pack(), "1321440", dict(runtime(), recipe_id="other")),
    (pack(), "1321440", dict(runtime(), pack_loading="adjacent")),
    (pack(), "1321440", dict(runtime(), engine_version="3.5.2")),
    (pack(), "1321440", []),
])
def test_profile_does_not_match_unrelated_exports(changed_pack, app_id, metadata):
    assert cassette_rendering_profile(changed_pack, app_id, metadata) is None


def test_profile_matches_exact_game_and_tested_runtime():
    assert cassette_rendering_profile(pack(), "1321440", runtime()) == CASSETTE_PROFILE_ID
    assert cassette_rendering_profile(replace(pack(), path=Path("CASSETTEBEASTS.pck")), "1321440", runtime()) == CASSETTE_PROFILE_ID


def test_quoted_depth_keys_are_replaced_and_duplicate_keys_rejected():
    merged = merge_depth_override('[rendering]\n"quality/depth_prepass/enable"=false\n')
    assert 'quality/depth_prepass/enable=true\n' in merged
    assert 'enable"=false' not in merged
    with pytest.raises(ValueError, match="Duplicate depth"):
        merge_depth_override('[rendering]\n"quality/depth_prepass/enable"=false\nquality/depth_prepass/enable=true\n')


def test_multiline_variants_cannot_be_mistaken_for_sections_or_depth_keys():
    value = '[other]\ntext="first line\n[rendering]\nquality/depth_prepass/enable=false\nlast line"\ndictionary={\n"array": [Vector2(1,2), Vector2(3,4)]\n}\n'
    merged = merge_depth_override(value)
    assert merged.startswith(value)
    assert merged.endswith('[rendering]\nquality/depth_prepass/disable_for_vendors=""\nquality/depth_prepass/enable=true\n')


@pytest.mark.parametrize("text", [
    '[other]\nvalue="unterminated\n',
    '[other]\nvalue={"a": [1,2}\n',
    '[rendering]\nquality/depth_prepass/disable_for_vendors="Adreno,\nApple"\n',
])
def test_unsafe_or_multiline_depth_values_are_not_silently_rewritten(text):
    with pytest.raises(ValueError, match="review before conversion"):
        merge_depth_override(text)


def test_launcher_applies_norp_only_for_selected_profile():
    selected = godot_launcher_body("game/CassetteBeasts.pck", disable_zink_render_pass_optimizations=True, force_gles3=True)
    assert 'export ZINK_DEBUG="${ZINK_DEBUG:+${ZINK_DEBUG},}norp"' in selected
    assert '--main-pack "$ROOT"/game/CassetteBeasts.pck' in selected
    assert '--video-driver GLES3' in selected
    assert "ZINK_DEBUG" not in godot_launcher_body("game/Other.pck")


def test_generated_launcher_executes_with_preserved_debug_flags_and_arguments(tmp_path):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash unavailable")
    root = tmp_path / "package with spaces"
    (root / "game").mkdir(parents=True)
    shim = root / "godot.arm64"
    shim.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$ZINK_DEBUG" "$@"\n', newline="\n")
    shim.chmod(0o755)
    launcher = root / "launch.sh"
    launcher.write_text(godot_launcher_body("game/CassetteBeasts.pck", disable_zink_render_pass_optimizations=True, force_gles3=True), newline="\n")
    env = dict(os.environ, ZINK_DEBUG="quiet")
    result = subprocess.run([bash, launcher.as_posix(), "argument with spaces"],
                            env=env, capture_output=True, text=True, check=True)
    lines = result.stdout.splitlines()
    assert lines[0] == "quiet,norp"
    assert lines[1] == "--main-pack"
    assert lines[2].endswith("/game/CassetteBeasts.pck")
    assert lines[3:] == ["--video-driver", "GLES3", "argument with spaces"]


def test_symlinked_override_never_modifies_original(tmp_path):
    original = tmp_path / "original.cfg"
    original.write_text('[rendering]\nquality/depth_prepass/enable=false\n')
    staging = tmp_path / "stage"
    game = staging / "game"
    game.mkdir(parents=True)
    try:
        (game / "override.cfg").symlink_to(original)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError, match="symlink"):
        install_cassette_rendering_profile(staging, game / "CassetteBeasts.pck")
    assert original.read_text().endswith("enable=false\n")
    assert not (staging / "godot-compatibility.json").exists()


@pytest.mark.parametrize("existing_override", [False, True])
def test_normal_conversion_and_zip_include_complete_profile(tmp_path, monkeypatch, existing_override):
    from test_godotsteam_provisioning import archive_fixture
    from megcfbt.router import build_source
    archive_fixture(tmp_path, monkeypatch, manifest_changes={"pack_loading": "main-pack"})
    source = tmp_path / "source"
    source.mkdir()
    (source / "CassetteBeasts.exe").write_bytes(b'MZ\0modules/godotsteam/godotsteam.cpp\0')
    (source / "CassetteBeasts.pck").write_bytes(struct.pack('<IIIII', 0x43504447, 1, 3, 5, 1) + b'\0' * 64 + struct.pack('<I', 0))
    (source / "steam_appid.txt").write_text('1321440\n')
    if existing_override:
        (source / "override.cfg").write_text('; keep\n[rendering]\nquality/depth_prepass/enable=false\nquality/shadows/filter_mode=2\n[other]\nvalue=Vector2(1,2)\n')
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir()}
    monkeypatch.setattr('megcfbt.router.host_can_build_automatic_runtime', lambda: False)
    monkeypatch.setattr('megcfbt.router.complete_frame_artwork', lambda *a, **k: None)
    result = build_source(source, output=tmp_path / 'output', archive=True)
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir()} == before
    override = result.output_path / 'game/override.cfg'
    assert 'quality/depth_prepass/disable_for_vendors=""' in override.read_text()
    assert 'quality/depth_prepass/enable=true' in override.read_text()
    if existing_override:
        assert 'value=Vector2(1,2)' in override.read_text()
        assert 'quality/shadows/filter_mode=2' in override.read_text()
    assert not (result.output_path / 'override.cfg').exists()
    receipt = json.loads((result.output_path / 'godot-compatibility.json').read_text())
    assert receipt['profile_id'] == CASSETTE_PROFILE_ID
    assert receipt['override_path'] == 'game/override.cfg'
    assert 'ZINK_DEBUG' in result.launcher_path.read_text()
    assert '--video-driver GLES3' in result.launcher_path.read_text()
    with zipfile.ZipFile(result.archive_path) as archive:
        assert archive.testzip() is None
        def content(suffix):
            return archive.read(next(name for name in archive.namelist() if name.endswith(suffix)))
        assert content('/payload/game/override.cfg') == override.read_bytes()
        assert content('/payload/godot-compatibility.json') == (result.output_path / 'godot-compatibility.json').read_bytes()
        assert content('/payload/godot.arm64') == (result.output_path / 'godot.arm64').read_bytes()
        assert content('/payload/launch.sh') == result.launcher_path.read_bytes()
