from pathlib import Path

import pytest

from renpy_arm.convert import (
    ConvertError,
    convert_game,
    detect_python_tag,
    detect_version,
    download_sdk,
    is_renpy_game,
    normalize_version,
    resolve_conversion_version,
    sync_engine_from_sdk,
    sync_runtime_support_from_sdk,
)
from renpy_arm.profiles import (
    KATAWA_PROFILE,
    detect_legacy_version,
    detect_profile,
    _katawa_variant,
    _modernize_katawa_hd_source,
    _overlay_hd_ui_assets,
    _overlay_user_katawa_archives,
)


def _legacy_root(tmp_path: Path, name: str = "Katawa Shoujo") -> Path:
    root = tmp_path / name
    (root / "renpy").mkdir(parents=True)
    (root / "game").mkdir()
    (root / "renpy" / "__init__.py").write_text(
        'version = "Ren\'Py 6.10.2e"\nscript_version = 5003000\n',
        encoding="utf-8",
    )
    return root


def _katawa_root(tmp_path: Path, name: str = "Katawa Shoujo") -> Path:
    root = _legacy_root(tmp_path, name)
    (root / "python25.dll").write_bytes(b"legacy-python")
    (root / "renpy.code").write_bytes(b"legacy-renpy")
    for filename in ("imachine.rpyc", "ui_settings.rpyc", "script-a1-monday.rpyc"):
        (root / "game" / filename).write_bytes(b"fixture")
    return root


def test_normalize_version_accepts_legacy_suffix() -> None:
    assert normalize_version("Ren'Py 6.10.2e") == "6.10.2"


def test_detect_version_reads_legacy_init(tmp_path: Path) -> None:
    root = _legacy_root(tmp_path)
    assert detect_legacy_version(root) == "6.10.2e"
    assert detect_version(root) == "6.10.2"


def test_legacy_distribution_is_recognized_as_renpy(tmp_path: Path) -> None:
    root = _legacy_root(tmp_path)
    (root / "python25.dll").write_bytes(b"fixture")
    assert is_renpy_game(root)


def test_katawa_profile_matches_without_folder_name(tmp_path: Path) -> None:
    root = _katawa_root(tmp_path, "some-random-folder")
    match = detect_profile(root)
    assert match is not None
    assert match.profile.id == KATAWA_PROFILE.id
    assert match.variant == "vanilla"


def test_katawa_hd_profile_matches_name(tmp_path: Path) -> None:
    root = _katawa_root(tmp_path, "Katawa Shoujo HD")
    match = detect_profile(root)
    assert match is not None
    assert match.variant == "hd"


def test_katawa_hd_profile_can_use_png_dimensions(tmp_path: Path) -> None:
    root = _katawa_root(tmp_path, "renamed-game")
    # Enough of a PNG header for the profile's IHDR size probe.
    header = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0d"
        + b"IHDR"
        + (1920).to_bytes(4, "big")
        + (1080).to_bytes(4, "big")
    )
    (root / "game" / "presplash.png").write_bytes(header)
    match = detect_profile(root)
    assert match is not None
    assert match.variant == "hd"


def test_profile_target_version_is_authoritative_after_migration(tmp_path: Path) -> None:
    legacy = _katawa_root(tmp_path)
    match = detect_profile(legacy)
    assert match is not None

    # Simulate a normalized packaged distribution that lacks source-form
    # version metadata. The profile already knows exactly what it produced.
    normalized = tmp_path / "normalized"
    normalized.mkdir()

    assert resolve_conversion_version(normalized, profile_match=match) == "8.0.3"


def test_unknown_legacy_game_gets_specific_error(tmp_path: Path) -> None:
    root = _legacy_root(tmp_path, "Other Legacy VN")
    (root / "python25.dll").write_bytes(b"fixture")

    with pytest.raises(ConvertError, match="Legacy Ren'Py 6.10.2e detected"):
        convert_game(root, work_dir=tmp_path / "work")


def test_katawa_hd_source_python2_syntax_is_modernized() -> None:
    source = (
        'print "JESUS CHRIST IT\'S A LION, DISABLE FULLSCREEN"\n'
        'try:\n'
        '    pass\n'
        'except Exception, e:\n'
        '    raise\n'
        '    import sets\n'
        '    chosen = sets.Set()\n'
        '    return renpy.display.render.Render(width, height, opaque=True)\n'
    )

    modern = _modernize_katawa_hd_source(source)

    assert 'print("JESUS CHRIST IT\'S A LION, DISABLE FULLSCREEN")' in modern
    assert "except Exception as e:" in modern
    assert "except Exception, e:" not in modern
    assert "import sets" not in modern
    assert "sets.Set()" not in modern
    assert "chosen = set()" in modern
    assert "Render(width, height, opaque=True)" not in modern
    assert "Render(width, height)" in modern


def test_katawa_hd_narrator_keeps_invisible_name_row() -> None:
    source = (
        '        store.narrator = Character(\' \', what_prefix="", what_suffix="", show_function=say_wrapper)\n'
        '    init_vars()\n'
        '    _game_menu_screen = "gm_bare"\n'
        '        if not who:\n'
        '            who = ""\n'
    )

    modern = _modernize_katawa_hd_source(source)

    assert "Character(NARRATOR_NAME" in modern
    assert 'NARRATOR_NAME = "{color=#0000}#{/color} "' in modern
    assert "who == NARRATOR_NAME" in modern


def test_katawa_hd_resource_archives_are_reapplied_with_priority(tmp_path: Path) -> None:
    source = tmp_path / "source"
    modern = tmp_path / "modern"
    (source / "game").mkdir(parents=True)
    (modern / "game").mkdir(parents=True)

    good = source / "game" / "img_ui.rpa"
    good.write_bytes(b"RPA-2.0 " + b"fixture")
    bad = source / "game" / "not-really.rpa"
    bad.write_bytes(b"NOTRPA!!")

    copied = _overlay_user_katawa_archives(source, modern, log=None)

    assert copied == 1
    dest = modern / "game" / "zz-renframe-hd-img_ui.rpa"
    assert dest.read_bytes() == good.read_bytes()
    assert not (modern / "game" / "zz-renframe-hd-not-really.rpa").exists()


def test_katawa_hd_context_and_script_compatibility_are_modernized() -> None:
    source = (
        "    def mm_context():\n"
        "        if is_glrenpy():\n"
        "            return renpy.context()._main_menu\n"
        "        else:\n"
        "            return renpy.context().main_menu\n"
        "    config.minimumvolume = -10.0\n"
        "    for pose, metadata in expressions.iteritems():\n"
    )

    modern = _modernize_katawa_hd_source(source)

    assert "return renpy.context().main_menu" not in modern
    assert "return renpy.context()._main_menu" in modern
    assert "config.script_version = (6,10,2)" in modern
    assert ".iteritems()" not in modern
    assert ".items()" in modern


def test_katawa_hd_variant_detects_source_layout_without_hd_folder_name(tmp_path: Path) -> None:
    game = tmp_path / "KatawaShoujo"
    payload = game / "game"
    payload.mkdir(parents=True)
    (payload / "ui_settings.rpy").write_text(
        "init -1 python:\n"
        "    style.default.size = 41\n"
        "    x = LiveComposite((1440, 1080), (0, 0), \"foo\")\n",
        encoding="utf-8",
    )

    assert _katawa_variant(game) == "hd"


def test_katawa_hd_archives_can_live_beside_launcher(tmp_path: Path) -> None:
    source = tmp_path / "source"
    modern = tmp_path / "modern"
    (source / "game").mkdir(parents=True)
    (modern / "game").mkdir(parents=True)

    root_archive = source / "img_ui.rpa"
    root_archive.write_bytes(b"RPA-2.0 " + b"fixture")

    copied = _overlay_user_katawa_archives(source, modern, log=None)

    assert copied == 1
    assert (modern / "game" / "zz-renframe-hd-img_ui.rpa").read_bytes() == root_archive.read_bytes()


def test_katawa_hd_archives_can_live_in_single_wrapper_parent(tmp_path: Path) -> None:
    wrapper = tmp_path / "wrapper"
    source = wrapper / "KatawaShoujo"
    modern = tmp_path / "modern"
    (source / "game").mkdir(parents=True)
    (modern / "game").mkdir(parents=True)

    wrapped_archive = wrapper / "img_ui.rpa"
    wrapped_archive.write_bytes(b"RPA-2.0 " + b"fixture")

    copied = _overlay_user_katawa_archives(source, modern, log=None)

    assert copied == 1
    assert (
        modern / "game" / "zz-renframe-hd-img_ui.rpa"
    ).read_bytes() == wrapped_archive.read_bytes()


def test_katawa_hd_ui_assets_are_overlaid_from_pinned_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modern = tmp_path / "modern"
    cache = tmp_path / "cache"
    (modern / "game").mkdir(parents=True)

    requested = []

    def fake_download(url, destination, *, force=False, log=None):
        requested.append((url, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"hd-ui")
        return destination

    monkeypatch.setattr("renpy_arm.profiles._download", fake_download)
    monkeypatch.setattr(
        "renpy_arm.profiles.KATAWA_HD_UI_FILES",
        ("game/ui/bg-say.png", "game/ui/bg-doublespeak.png"),
    )

    copied = _overlay_hd_ui_assets(
        modern,
        cache,
        force=False,
        log=None,
    )

    assert copied == 2
    assert (modern / "game" / "ui" / "bg-say.png").read_bytes() == b"hd-ui"
    assert (modern / "game" / "ui" / "bg-doublespeak.png").read_bytes() == b"hd-ui"
    assert len(requested) == 2


def test_detect_version_reads_modern_script_version_file(tmp_path: Path) -> None:
    root = tmp_path / "Modern Game"
    (root / "game").mkdir(parents=True)
    (root / "renpy").mkdir()
    (root / "lib").mkdir()
    (root / "game" / "script_version.txt").write_text(
        "(8, 4, 1)",
        encoding="utf-8",
    )

    assert detect_version(root) == "8.4.1"


def test_detect_version_reads_version_tuple_from_init(tmp_path: Path) -> None:
    root = tmp_path / "Modern Game"
    (root / "game").mkdir(parents=True)
    (root / "renpy").mkdir()
    (root / "lib").mkdir()
    (root / "renpy" / "__init__.py").write_text(
        "version_tuple = (8, 4, 1, vc_version)\n",
        encoding="utf-8",
    )

    assert detect_version(root) == "8.4.1"


def test_download_sdk_falls_back_within_same_minor_on_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error

    attempts = []

    def fake_urlretrieve(url, destination, reporthook=None):
        attempts.append(url)
        if "/8.4.2/" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        Path(destination).write_bytes(b"sdk-fixture")
        return destination, None

    monkeypatch.setattr("renpy_arm.convert.urllib.request.urlretrieve", fake_urlretrieve)

    sdk, runtime_version = download_sdk("8.4.2", tmp_path, force=False)

    assert runtime_version == "8.4.1"
    assert sdk.name == "renpy-8.4.1-sdkarm.tar.bz2"
    assert any("/8.4.2/" in url for url in attempts)
    assert any("/8.4.1/" in url for url in attempts)


def test_download_sdk_does_not_cross_minor_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error

    attempts = []

    def fake_urlretrieve(url, destination, reporthook=None):
        attempts.append(url)
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr("renpy_arm.convert.urllib.request.urlretrieve", fake_urlretrieve)

    with pytest.raises(ConvertError, match="No published ARM SDK found"):
        download_sdk("8.4.0", tmp_path, force=False)

    assert all("/8.4." in url for url in attempts)


def test_download_sdk_bridges_renpy_7_4_to_7_5_arm_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = []

    def fake_urlretrieve(url, destination, reporthook=None):
        attempts.append(url)
        Path(destination).write_bytes(b"sdk-fixture")
        return destination, None

    monkeypatch.setattr("renpy_arm.convert.urllib.request.urlretrieve", fake_urlretrieve)

    sdk, runtime_version = download_sdk("7.4.6", tmp_path, force=False)

    assert runtime_version == "7.5.3"
    assert sdk.name == "renpy-7.5.3-sdkarm.tar.bz2"
    assert attempts == [
        "https://www.renpy.org/dl/7.5.3/renpy-7.5.3-sdkarm.tar.bz2"
    ]


def test_download_sdk_rejects_pre_7_4_without_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = []

    def fake_urlretrieve(url, destination, reporthook=None):
        attempts.append(url)
        Path(destination).write_bytes(b"sdk-fixture")
        return destination, None

    monkeypatch.setattr("renpy_arm.convert.urllib.request.urlretrieve", fake_urlretrieve)

    with pytest.raises(ConvertError, match="needs a compatibility profile"):
        download_sdk("6.18.3", tmp_path, force=False)

    assert attempts == []


def test_detect_python_tag_uses_renpy_major_for_legacy_lib_layout(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Legacy7"
    (root / "lib" / "windows-x86_64").mkdir(parents=True)

    assert detect_python_tag(root, "7.4.6") == "py2"


def test_detect_python_tag_uses_renpy_major_when_both_runtime_families_exist(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Mixed"
    (root / "lib" / "py2-windows-x86_64").mkdir(parents=True)
    (root / "lib" / "py3-windows-x86_64").mkdir(parents=True)

    assert detect_python_tag(root, "7.8.7") == "py2"
    assert detect_python_tag(root, "8.3.7") == "py3"


@pytest.mark.parametrize(
    ("source_version", "runtime_version"),
    [
        ("7.5.0", "7.5.3"),
        ("7.5.1", "7.5.3"),
        ("8.0.0", "8.0.3"),
        ("8.0.1", "8.0.3"),
        ("7.7.2", "7.7.3"),
        ("8.2.2", "8.2.3"),
    ],
)
def test_download_sdk_redirects_known_broken_release_builds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_version: str,
    runtime_version: str,
) -> None:
    attempts = []

    def fake_urlretrieve(url, destination, reporthook=None):
        attempts.append(url)
        Path(destination).write_bytes(b"sdk-fixture")
        return destination, None

    monkeypatch.setattr("renpy_arm.convert.urllib.request.urlretrieve", fake_urlretrieve)

    sdk, selected = download_sdk(source_version, tmp_path, force=False)

    assert selected == runtime_version
    assert sdk.name == f"renpy-{runtime_version}-sdkarm.tar.bz2"
    assert attempts == [
        f"https://www.renpy.org/dl/{runtime_version}/"
        f"renpy-{runtime_version}-sdkarm.tar.bz2"
    ]


def test_sync_engine_from_sdk_replaces_mismatched_engine_tree(tmp_path: Path) -> None:
    import tarfile

    game = tmp_path / "game-root"
    (game / "renpy").mkdir(parents=True)
    (game / "renpy" / "__init__.py").write_text(
        'version = "7.4.6"\n',
        encoding="utf-8",
    )
    (game / "renpy" / "old-only.py").write_text("old\n", encoding="utf-8")

    sdk_root = tmp_path / "sdk-root" / "renpy-7.5.3-sdk"
    (sdk_root / "renpy" / "common").mkdir(parents=True)
    (sdk_root / "renpy" / "__init__.py").write_text(
        'version = "7.5.3"\n',
        encoding="utf-8",
    )
    (sdk_root / "renpy" / "common" / "00start.rpy").write_text(
        "# matching common scripts\n",
        encoding="utf-8",
    )

    sdk = tmp_path / "renpy-7.5.3-sdkarm.tar.bz2"
    with tarfile.open(sdk, "w:bz2") as tf:
        tf.add(sdk_root, arcname="renpy-7.5.3-sdk")

    sync_engine_from_sdk(sdk, game, "7.4.6", "7.5.3")

    assert '7.5.3' in (game / "renpy" / "__init__.py").read_text(encoding="utf-8")
    assert (game / "renpy" / "common" / "00start.rpy").is_file()
    assert not (game / "renpy" / "old-only.py").exists()


def test_sync_engine_from_sdk_is_noop_for_exact_runtime(tmp_path: Path) -> None:
    game = tmp_path / "game-root"
    (game / "renpy").mkdir(parents=True)
    marker = game / "renpy" / "keep-me.py"
    marker.write_text("keep\n", encoding="utf-8")

    sync_engine_from_sdk(
        tmp_path / "does-not-need-to-exist.tar.bz2",
        game,
        "8.3.7",
        "8.3.7",
    )

    assert marker.read_text(encoding="utf-8") == "keep\n"


def test_sync_runtime_support_from_sdk_merges_shared_python_files(
    tmp_path: Path,
) -> None:
    import tarfile

    game = tmp_path / "game-root"
    (game / "lib" / "python2.7").mkdir(parents=True)
    (game / "lib" / "python2.7" / "old_runtime.py").write_text(
        "old\n",
        encoding="utf-8",
    )

    sdk_root = tmp_path / "sdk-root" / "renpy-7.5.3-sdk"
    arm = sdk_root / "lib" / "py2-linux-aarch64"
    arm.mkdir(parents=True)
    (arm / "librenpython.so").write_bytes(b"arm-runtime")
    shared = sdk_root / "lib" / "python2.7"
    shared.mkdir(parents=True)
    (shared / "typing.py").write_text(
        "# python2 typing backport\n",
        encoding="utf-8",
    )
    other_platform = sdk_root / "lib" / "py3-linux-aarch64"
    other_platform.mkdir(parents=True)
    (other_platform / "should-not-copy").write_text("no\n", encoding="utf-8")

    sdk = tmp_path / "renpy-7.5.3-sdkarm.tar.bz2"
    with tarfile.open(sdk, "w:bz2") as tf:
        tf.add(sdk_root, arcname="renpy-7.5.3-sdk")

    sync_runtime_support_from_sdk(
        sdk,
        game,
        python_tag="py2",
        runtime_version="7.5.3",
    )

    assert (game / "lib" / "python2.7" / "typing.py").is_file()
    assert (game / "lib" / "python2.7" / "old_runtime.py").is_file()
    assert not (game / "lib" / "py3-linux-aarch64").exists()
