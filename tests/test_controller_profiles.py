"""Profile semantics, portable packaging and reversible per-shortcut selection."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from megcfbt.controller_profiles import CONTROLLERS, ENGINES, prepare_profile, profile_text
from megcfbt.controller_support import setup


def parse_vdf(text):
    tokens = iter(re.findall(r'"(?:\\.|[^"\\])*"|[{}]', text))
    def obj(nested=False):
        pairs = []
        for token in tokens:
            if token == "}":
                assert nested
                return pairs
            key = json.loads(token)
            value = next(tokens)
            pairs.append((key, obj(True) if value == "{" else json.loads(value)))
        assert not nested
        return pairs
    return dict(obj())["controller_mappings"]


def binding(group, input_name):
    inputs = dict(group)["inputs"]
    return dict(dict(dict(dict(inputs)[input_name])["activators"])["Full_Press"])["bindings"][0][1]


@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_both_modes_keep_directions_and_only_pointer_mode_sends_mouse(engine):
    profile = parse_vdf(profile_text(engine, "controller_steamframe_pair"))
    groups = {dict(g)["id"]: g for k, g in profile if k == "group"}
    modes = {dict(p)["name"]: dict(dict(p)["group_source_bindings"]) for k, p in profile if k == "preset"}
    assert set(modes) == {"Game controls", "Pointer mode"}
    normal, pointer = modes["Game controls"], modes["Pointer mode"]
    for mode in modes.values():
        assert len(mode) == 7
        for source in ("dpad active", "joystick active"):
            group, = [groups[k] for k, value in mode.items() if value == source]
            assert binding(group, "dpad_north") == "key_press UP_ARROW, Up"
    normal_id, = [k for k, v in normal.items() if v == "right_joystick active"]
    pointer_id, = [k for k, v in pointer.items() if v == "right_joystick active"]
    assert dict(groups[normal_id])["mode"] == "joystick_move"
    assert dict(groups[pointer_id])["mode"] == "joystick_mouse"
    assert "CHANGE_PRESET 2 " in binding(groups[normal_id], "click")
    assert "CHANGE_PRESET 1 " in binding(groups[pointer_id], "click")
    for source, expected in (("left_trigger active", "RIGHT"), ("right_trigger active", "LEFT")):
        group_id, = [k for k, value in pointer.items() if value == source]
        assert binding(groups[group_id], "edge").startswith("mouse_button " + expected)
        normal_id, = [k for k, value in normal.items() if value == source]
        assert binding(groups[normal_id], "click").startswith("xinput_button ")
        assert dict(dict(groups[normal_id])["settings"])["output_trigger"] == ("1" if source == "left_trigger active" else "2")
        assert dict(dict(groups[group_id])["settings"])["output_trigger"] == "0"


@pytest.mark.parametrize("kind", CONTROLLERS)
def test_generated_controller_types_and_tuning(kind):
    profile = dict(parse_vdf(profile_text("renpy", kind, sensitivity=125, deadzone=9000)))
    assert profile["controller_type"] == kind
    text = profile_text("renpy", kind, sensitivity=125, deadzone=9000)
    assert '"deadzone_inner_radius"\t"9000"' in text
    assert '"sensitivity"\t"125"' in text


@pytest.mark.parametrize("kwargs", [{"engine": "godot"}, {"controller_type": "../oops"},
                                    {"sensitivity": 0}, {"deadzone": 21000}])
def test_invalid_profile_rejected(kwargs):
    args = dict(engine="mv", controller_type="controller_generic")
    args.update(kwargs)
    with pytest.raises(ValueError):
        profile_text(**args)


def test_prepare_publishes_only_own_templates_and_portable_helper(tmp_path):
    build = tmp_path / "build"
    directory = prepare_profile(build, "mv")
    manifest = json.loads((directory / "profile.json").read_text())
    for entry in manifest["controllers"].values():
        assert hashlib.sha256((directory / entry["file"]).read_bytes()).hexdigest() == entry["sha256"]
    # The portable helper imports from its own directory without the repository.
    result = subprocess.run([sys.executable, str(directory / "setup.py"), "--help"],
                            cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "--apply" in result.stdout and "--restore" in result.stdout
    steam = tmp_path / "Steam"
    (steam / "controller_base/templates").mkdir(parents=True)
    personal = steam / "controller_base/templates/personal.vdf"
    personal.write_text("my existing layout")
    url = setup.publish(directory, "controller_steamframe_pair", steam)
    assert url.startswith("template://megcfbt-controller-pointer-v1-")
    assert setup.publish(directory, "controller_steamframe_pair", steam) == url
    assert personal.read_text() == "my existing layout"
    with pytest.raises(ValueError):
        prepare_profile(build, "mv")


def test_modified_profile_cannot_be_published(tmp_path):
    directory = prepare_profile(tmp_path / "build", "mv")
    next(directory.glob("*.vdf")).write_text("corrupt")
    manifest = json.loads((directory / "profile.json").read_text())
    corrupt = next(k for k, v in manifest["controllers"].items() if (directory / v["file"]).read_text() == "corrupt")
    with pytest.raises(ValueError, match="checksum"):
        setup.publish(directory, corrupt, tmp_path)


class Steam:
    def __init__(self):
        self.url = "template://original.vdf"
        self.enabled = True
        self.calls = []
    def __call__(self, script):
        self.calls.append(script)
        if "ClearSelectedConfigForApp" in script:
            self.url = "default://original"
            return True
        if "SetSelectedConfigForApp" in script:
            args = re.search(r'SetSelectedConfigForApp\(123,0,("[^"]+"),false,0\)', script)
            assert args
            self.url = json.loads(args.group(1))
            return True
        if "PreviewConfigForAppAndController" in script:
            assert "data.byteLength" in script
            return {"bytes": 2048}
        return {"URL": self.url, "bConfigurationEnabled": self.enabled}


def test_apply_and_restore_retain_the_original_selection(tmp_path):
    steam = Steam()
    receipt = tmp_path / "selection.json"
    setup.apply(123, 0, "template://new.vdf", receipt, steam)
    assert steam.url == "template://new.vdf"
    assert json.loads(receipt.read_text())["before_url"] == "template://original.vdf"
    setup.restore(receipt, steam)
    assert steam.url == "template://original.vdf"
    assert not receipt.exists()
    assert list(tmp_path.glob("*.restored-*.json"))


def test_disabled_steam_input_and_existing_receipt_prevent_changes(tmp_path):
    steam = Steam()
    steam.enabled = False
    receipt = tmp_path / "selection.json"
    with pytest.raises(ValueError, match="Enable Steam Input"):
        setup.apply(123, 0, "template://new.vdf", receipt, steam)
    assert not receipt.exists()
    receipt.write_text("existing backup")
    steam.enabled = True
    with pytest.raises(ValueError, match="backup already exists"):
        setup.apply(123, 0, "template://new.vdf", receipt, steam)
    assert steam.url == "template://original.vdf"


def test_restore_does_not_replace_a_later_user_choice(tmp_path):
    steam = Steam()
    receipt = tmp_path / "selection.json"
    setup.apply(123, 0, "template://new.vdf", receipt, steam)
    steam.url = "template://personal-edit.vdf"
    with pytest.raises(ValueError, match="newer selection"):
        setup.restore(receipt, steam)
    assert steam.url == "template://personal-edit.vdf" and receipt.exists()


def test_restoring_a_default_clears_the_explicit_selection(tmp_path):
    steam = Steam()
    steam.url = "default://original"
    receipt = tmp_path / "selection.json"
    setup.apply(123, 0, "template://new.vdf", receipt, steam)
    setup.restore(receipt, steam)
    assert steam.url == "default://original"
    assert any("ClearSelectedConfigForApp(123,0,0)" in call for call in steam.calls)


@pytest.mark.parametrize('enabled', [False, True])
def test_unified_build_bundles_profile_only_when_requested(tmp_path, monkeypatch, enabled):
    from types import SimpleNamespace
    import zipfile
    from megcfbt.router import build_source
    source = tmp_path / 'source'
    (source / 'www/js').mkdir(parents=True)
    (source / 'www/data').mkdir()
    original = 'Utils.RPGMAKER_VERSION = "1.6.1";'
    (source / 'www/js/rpg_core.js').write_text(original)
    (source / 'www/data/System.json').write_text('{"gameTitle":"Input test"}')
    (source / 'www/index.html').write_text('<html></html>')
    (source / 'package.json').write_text('{"main":"www/index.html"}')
    output = tmp_path / 'converted'
    def backend(*args, **kwargs):
        output.mkdir()
        launcher = output / 'launch.sh'
        launcher.write_text('#!/bin/sh\n')
        return SimpleNamespace(launcher_path=launcher, warnings=[], game_name='Input test', engine_version='1.6.1')
    monkeypatch.setattr('megcfbt.router.build_rpgm_game', backend)
    result = build_source(source, output=output, controller_profile=enabled,
                          steamgriddb_game_id=None, archive=True)
    assert (source / 'www/js/rpg_core.js').read_text() == original
    assert (output / '.megcfbt/controllers/profile.json').exists() == enabled
    with zipfile.ZipFile(result.archive_path) as archive:
        profiles = [name for name in archive.namelist() if name.endswith('/controllers/profile.json')]
        assert bool(profiles) == enabled


def test_cli_adds_profile_to_existing_build_without_changing_launcher(tmp_path):
    from megcfbt.cli import main
    from megcfbt.frame_package import write_frame_metadata
    launcher = tmp_path / 'launch.sh'
    launcher.write_text('#!/bin/sh\nexit 0\n')
    write_frame_metadata(tmp_path, name='Test', launcher_path=launcher, engine='renpy')
    assert main(['controller-profile', str(tmp_path), '--sensitivity', '125']) == 0
    manifest = json.loads((tmp_path / '.megcfbt/controllers/profile.json').read_text())
    assert manifest['engine'] == 'renpy' and manifest['sensitivity'] == 125
    assert launcher.read_text() == '#!/bin/sh\nexit 0\n'


def test_unsupported_controller_opt_in_stops_before_building(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from megcfbt.router import build_source, ConversionError
    monkeypatch.setattr('megcfbt.router.inspect_source', lambda _: SimpleNamespace(engine='godot'))
    with pytest.raises(ConversionError, match="Ren'Py and RPG Maker only"):
        build_source(tmp_path / 'source', output=tmp_path / 'output', controller_profile=True)
    assert not (tmp_path / 'output').exists()


def test_frame_routing_is_explicit_and_validates_parent_and_collisions():
    parent = 0x81012345
    alias = parent & 0xFFFFFF
    scripts = []
    def evaluate(script):
        scripts.append(script)
        return {'URL': 'default://routing', 'bConfigurationEnabled': True}
    setup.selection(alias, 0, evaluate, shortcut_id=parent)
    assert f'a.appid==={parent}&&a.app_type===1073741824' in scripts[-1]
    assert f'if (appStore.allApps.some(a=>a.appid==={alias} ||' in scripts[-1]
    assert f'a.appid!=={parent} && (a.appid & 0xFFFFFF)==={alias}' in scripts[-1]
    with pytest.raises(ValueError, match='Invalid Frame routing'):
        setup.selection(alias + 1, 0, evaluate, shortcut_id=parent)
    with pytest.raises(ValueError, match='Invalid Frame routing'):
        setup.selection(769, 0, evaluate, shortcut_id=0x81000301)


def test_frame_routing_backup_restores_only_its_own_selection(tmp_path):
    parent, alias = 0x81012345, 0x12345
    state = {'URL': 'default://routing', 'bConfigurationEnabled': True}
    calls = []
    def evaluate(script):
        calls.append(script)
        if 'PreviewConfigForAppAndController' in script:
            return {'bytes': 2000}
        if 'SetSelectedConfigForApp' in script:
            state['URL'] = 'template://new.vdf'
            return True
        if 'ClearSelectedConfigForApp' in script:
            state['URL'] = 'default://routing'
            return True
        return dict(state)
    receipt = tmp_path / 'routing.json'
    setup.apply(alias, 0, 'template://new.vdf', receipt, evaluate, shortcut_id=parent)
    assert json.loads(receipt.read_text())['shortcut_id'] == parent
    setup.restore(receipt, evaluate)
    assert state['URL'] == 'default://routing'
    assert all(f'{parent},0' not in call for call in calls if 'SelectedConfigForApp' in call)


def test_receipt_creation_never_overwrites_a_concurrent_backup(tmp_path):
    receipt = tmp_path / 'selection.json'
    receipt.write_text('original backup')
    with pytest.raises(FileExistsError):
        setup._write_receipt(receipt, {'before_url': 'wrong backup'})
    assert receipt.read_text() == 'original backup'


def test_restore_rejects_a_different_controller_at_the_saved_index(tmp_path):
    steam = Steam()
    kind = [21]
    def evaluate(script):
        result = steam(script)
        if isinstance(result, dict) and 'URL' in result:
            result['nControllerType'] = kind[0]
        return result
    receipt = tmp_path / 'selection.json'
    setup.apply(123, 0, 'template://new.vdf', receipt, evaluate)
    kind[0] = 50
    with pytest.raises(ValueError, match='controller at this index changed'):
        setup.restore(receipt, evaluate)
    assert receipt.exists() and steam.url == 'template://new.vdf'
    kind[0] = 21
    setup.restore(receipt, evaluate)
    assert steam.url == 'template://original.vdf'


def test_unsupported_selection_type_leaves_steam_and_backups_untouched(tmp_path):
    steam = Steam()
    def evaluate(script):
        result = steam(script)
        if isinstance(result, dict) and 'URL' in result:
            result['eSelectionType'] = 1
        return result
    receipt = tmp_path / 'selection.json'
    with pytest.raises(ValueError, match='selection type is not supported'):
        setup.apply(123, 0, 'template://new.vdf', receipt, evaluate)
    assert steam.url == 'template://original.vdf' and not receipt.exists()
