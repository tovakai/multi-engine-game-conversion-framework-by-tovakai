from pathlib import Path
import pytest
from renframe.profiles import KATAWA_PROFILE, detect_legacy_version, detect_profile, _katawa_variant, _modernize_katawa_hd_source, _overlay_hd_ui_assets, _overlay_user_katawa_archives

def test_katawa_hd_window_close_uses_existing_modern_menu_label():
    source = "label quit_from_os:\n\n    if is_glrenpy():\n        $ _enter_menu()\n    elif True:\n        call _enter_menu from quit_from_os_1\n    $ quit_from_os_flag = True\n"
    modern = _modernize_katawa_hd_source(source)
    assert 'call _enter_game_menu from quit_from_os_1' in modern
    assert '_enter_menu' not in modern
    assert '$ quit_from_os_flag = True' in modern

def _legacy_root(tmp_path: Path, name: str='Katawa Shoujo') -> Path:
    root = tmp_path / name
    (root / 'renpy').mkdir(parents=True)
    (root / 'game').mkdir()
    (root / 'renpy' / '__init__.py').write_text('version = "Ren\'Py 6.10.2e"\nscript_version = 5003000\n', encoding='utf-8')
    return root

def _katawa_root(tmp_path: Path, name: str='Katawa Shoujo') -> Path:
    root = _legacy_root(tmp_path, name)
    (root / 'python25.dll').write_bytes(b'legacy-python')
    (root / 'renpy.code').write_bytes(b'legacy-renpy')
    for filename in ('imachine.rpyc', 'ui_settings.rpyc', 'script-a1-monday.rpyc'):
        (root / 'game' / filename).write_bytes(b'fixture')
    return root

def test_katawa_profile_matches_without_folder_name(tmp_path: Path) -> None:
    root = _katawa_root(tmp_path, 'some-random-folder')
    match = detect_profile(root)
    assert match is not None
    assert match.profile.id == KATAWA_PROFILE.id
    assert match.variant == 'vanilla'

def test_katawa_hd_profile_matches_name(tmp_path: Path) -> None:
    root = _katawa_root(tmp_path, 'Katawa Shoujo HD')
    match = detect_profile(root)
    assert match is not None
    assert match.variant == 'hd'

def test_katawa_hd_profile_can_use_png_dimensions(tmp_path: Path) -> None:
    root = _katawa_root(tmp_path, 'renamed-game')
    header = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\r' + b'IHDR' + 1920 .to_bytes(4, 'big') + 1080 .to_bytes(4, 'big')
    (root / 'game' / 'presplash.png').write_bytes(header)
    match = detect_profile(root)
    assert match is not None
    assert match.variant == 'hd'

def test_katawa_hd_source_python2_syntax_is_modernized() -> None:
    source = 'print "JESUS CHRIST IT\'S A LION, DISABLE FULLSCREEN"\ntry:\n    pass\nexcept Exception, e:\n    raise\n    import sets\n    chosen = sets.Set()\n    return renpy.display.render.Render(width, height, opaque=True)\n'
    modern = _modernize_katawa_hd_source(source)
    assert 'print("JESUS CHRIST IT\'S A LION, DISABLE FULLSCREEN")' in modern
    assert 'except Exception as e:' in modern
    assert 'except Exception, e:' not in modern
    assert 'import sets' not in modern
    assert 'sets.Set()' not in modern
    assert 'chosen = set()' in modern
    assert 'Render(width, height, opaque=True)' not in modern
    assert 'Render(width, height)' in modern

def test_katawa_hd_narrator_keeps_invisible_name_row() -> None:
    source = '        store.narrator = Character(\' \', what_prefix="", what_suffix="", show_function=say_wrapper)\n    init_vars()\n    _game_menu_screen = "gm_bare"\n        if not who:\n            who = ""\n'
    modern = _modernize_katawa_hd_source(source)
    assert 'Character(NARRATOR_NAME' in modern
    assert 'NARRATOR_NAME = "{color=#0000}#{/color} "' in modern
    assert 'who == NARRATOR_NAME' in modern

def test_katawa_hd_resource_archives_are_reapplied_with_priority(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    modern = tmp_path / 'modern'
    (source / 'game').mkdir(parents=True)
    (modern / 'game').mkdir(parents=True)
    good = source / 'game' / 'img_ui.rpa'
    good.write_bytes(b'RPA-2.0 ' + b'fixture')
    bad = source / 'game' / 'not-really.rpa'
    bad.write_bytes(b'NOTRPA!!')
    copied = _overlay_user_katawa_archives(source, modern, log=None)
    assert copied == 1
    dest = modern / 'game' / 'zz-renframe-hd-img_ui.rpa'
    assert dest.read_bytes() == good.read_bytes()
    assert not (modern / 'game' / 'zz-renframe-hd-not-really.rpa').exists()

def test_katawa_hd_context_and_script_compatibility_are_modernized() -> None:
    source = '    def mm_context():\n        if is_glrenpy():\n            return renpy.context()._main_menu\n        else:\n            return renpy.context().main_menu\n    config.minimumvolume = -10.0\n    for pose, metadata in expressions.iteritems():\n'
    modern = _modernize_katawa_hd_source(source)
    assert 'return renpy.context().main_menu' not in modern
    assert 'return renpy.context()._main_menu' in modern
    assert 'config.script_version = (6,10,2)' in modern
    assert '.iteritems()' not in modern
    assert '.items()' in modern

def test_katawa_hd_variant_detects_source_layout_without_hd_folder_name(tmp_path: Path) -> None:
    game = tmp_path / 'KatawaShoujo'
    payload = game / 'game'
    payload.mkdir(parents=True)
    (payload / 'ui_settings.rpy').write_text('init -1 python:\n    style.default.size = 41\n    x = LiveComposite((1440, 1080), (0, 0), "foo")\n', encoding='utf-8')
    assert _katawa_variant(game) == 'hd'

def test_katawa_hd_archives_can_live_beside_launcher(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    modern = tmp_path / 'modern'
    (source / 'game').mkdir(parents=True)
    (modern / 'game').mkdir(parents=True)
    root_archive = source / 'img_ui.rpa'
    root_archive.write_bytes(b'RPA-2.0 ' + b'fixture')
    copied = _overlay_user_katawa_archives(source, modern, log=None)
    assert copied == 1
    assert (modern / 'game' / 'zz-renframe-hd-img_ui.rpa').read_bytes() == root_archive.read_bytes()

def test_katawa_hd_archives_can_live_in_single_wrapper_parent(tmp_path: Path) -> None:
    wrapper = tmp_path / 'wrapper'
    source = wrapper / 'KatawaShoujo'
    modern = tmp_path / 'modern'
    (source / 'game').mkdir(parents=True)
    (modern / 'game').mkdir(parents=True)
    wrapped_archive = wrapper / 'img_ui.rpa'
    wrapped_archive.write_bytes(b'RPA-2.0 ' + b'fixture')
    copied = _overlay_user_katawa_archives(source, modern, log=None)
    assert copied == 1
    assert (modern / 'game' / 'zz-renframe-hd-img_ui.rpa').read_bytes() == wrapped_archive.read_bytes()

def test_katawa_hd_ui_assets_are_overlaid_from_pinned_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modern = tmp_path / 'modern'
    cache = tmp_path / 'cache'
    (modern / 'game').mkdir(parents=True)
    requested = []

    def fake_download(url, destination, *, force=False, log=None):
        requested.append((url, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b'hd-ui')
        return destination
    monkeypatch.setattr('renframe.profiles._download', fake_download)
    monkeypatch.setattr('renframe.profiles.KATAWA_HD_UI_FILES', ('game/ui/bg-say.png', 'game/ui/bg-doublespeak.png'))
    copied = _overlay_hd_ui_assets(modern, cache, force=False, log=None)
    assert copied == 2
    assert (modern / 'game' / 'ui' / 'bg-say.png').read_bytes() == b'hd-ui'
    assert (modern / 'game' / 'ui' / 'bg-doublespeak.png').read_bytes() == b'hd-ui'
    assert len(requested) == 2
