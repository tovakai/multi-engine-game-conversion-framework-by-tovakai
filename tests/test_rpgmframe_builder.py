from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

import pytest

from rpgmframe.builder import BuildError, build_game
from rpgmframe.models import EngineVariant


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_elf(path: Path, machine: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[6] = 1
    header[18:20] = machine.to_bytes(2, "little")
    path.write_bytes(header)


def _mv_game(root: Path) -> Path:
    wrapper = root / "jailbreak_win"
    _write(
        wrapper / "www/js/rpg_core.js",
        'Utils.RPGMAKER_VERSION = "1.6.1";\nvar meter = new FPSMeter();\n',
    )
    _write(wrapper / "www/data/System.json", json.dumps({"gameTitle": "Test MV"}))
    _write(
        wrapper / "www/index.html",
        '<html><head><script type="text/javascript" src="js/rpg_core.js"></script></head></html>',
    )
    _write(wrapper / "www/js/libs/fpsmeter.js", "window.FPSMeter = function() {};")
    _write(wrapper / "www/js/plugins.js", "var $plugins = [];")
    _write(
        wrapper / "package.json",
        json.dumps(
            {
                "name": "",
                "main": "www/index.html",
                "js-flags": "--expose-gc",
                "window": {"width": 816, "height": 624},
            }
        ),
    )
    return root


def _runtime(root: Path, machine: int = 183) -> Path:
    _write_elf(root / "nw", machine)
    _write_elf(root / "chrome_crashpad_handler", machine)
    _write(root / "resources.pak", "runtime")
    return root


def test_builds_mv_with_arm64_nwjs(tmp_path: Path) -> None:
    source = _mv_game(tmp_path / "source")
    runtime = _runtime(tmp_path / "nwjs")
    output = tmp_path / "built"

    result = build_game(source, runtime=runtime, output=output)

    assert result.success
    assert result.runtime_architecture == "aarch64"
    assert (output / "nw").is_file()
    assert (output / "resources.pak").is_file()
    assert (output / "www/js/rpg_core.js").is_file()
    assert (output / "www/data/System.json").is_file()
    assert (output / "launch.sh").is_file()
    assert (output / "www/js/rpgmframe-compat.js").is_file()

    index_html = (output / "www/index.html").read_text(encoding="utf-8")
    assert "js/rpgmframe-compat.js" in index_html
    assert "js/libs/fpsmeter.js" in index_html
    assert index_html.index("rpgmframe-compat.js") < index_html.index("rpg_core.js")
    assert index_html.index("fpsmeter.js") < index_html.index("rpg_core.js")

    package = json.loads((output / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == "rpgmframe-source"
    assert package["main"] == "www/index.html"
    assert package["js-flags"] == "--expose-gc"
    assert package["window"]["width"] == 816

    launcher = (output / "launch.sh").read_text(encoding="utf-8")
    assert "plasmashell" in launcher
    assert "XAUTHORITY" in launcher
    assert "LOCALAPPDATA" in launcher
    assert "APPDATA" in launcher
    assert "USERPROFILE" in launcher
    assert 'cd "$ROOT"' in launcher
    assert 'exec "$ROOT/nw" "$ROOT" "$@"' in launcher


def test_rejects_x86_64_runtime(tmp_path: Path) -> None:
    source = _mv_game(tmp_path / "source")
    runtime = _runtime(tmp_path / "nwjs", machine=62)

    with pytest.raises(BuildError, match="x86_64, not aarch64"):
        build_game(source, runtime=runtime, output=tmp_path / "built")


def test_builds_mz_with_arm64_nwjs(tmp_path: Path) -> None:
    source = tmp_path / "mz"
    _write(source / "js/rmmz_core.js", 'Utils.RPGMAKER_VERSION = "1.8.1";')
    _write(source / "js/rmmz_managers.js", "/* managers */")
    _write(source / "data/System.json", json.dumps({"gameTitle": "Test MZ"}))
    _write(source / "index.html", "<html>mz</html>")
    _write(source / "icon/icon.png", "icon")
    _write(
        source / "package.json",
        json.dumps(
            {
                "name": "rmmz-game",
                "main": "index.html",
                "chromium-args": "--force-color-profile=srgb --disable-devtools",
                "window": {
                    "title": "Test MZ",
                    "width": 816,
                    "height": 624,
                    "icon": "icon/icon.png",
                },
            }
        ),
    )
    runtime = _runtime(tmp_path / "nwjs")
    output = tmp_path / "built"

    result = build_game(source, runtime=runtime, output=output)

    assert result.success
    assert result.engine.value == "mz"
    assert (output / "www/js/rmmz_core.js").is_file()
    assert (output / "www/js/rmmz_managers.js").is_file()
    assert (output / "www/index.html").is_file()
    assert (output / "www/icon/icon.png").is_file()

    package = json.loads((output / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == "rmmz-game"
    assert package["main"] == "www/index.html"
    assert package["chromium-args"] == "--force-color-profile=srgb --disable-devtools"
    assert package["window"]["icon"] == "www/icon/icon.png"
    assert not any("experimental" in warning.lower() for warning in result.warnings)


def test_force_replaces_existing_output(tmp_path: Path) -> None:
    source = _mv_game(tmp_path / "source")
    runtime = _runtime(tmp_path / "nwjs")
    output = tmp_path / "built"
    output.mkdir()
    _write(output / "old.txt", "old")

    with pytest.raises(BuildError, match="already exists"):
        build_game(source, runtime=runtime, output=output)

    build_game(source, runtime=runtime, output=output, force=True)

    assert not (output / "old.txt").exists()
    assert (output / "www/index.html").is_file()


def test_build_can_resolve_runtime_automatically(tmp_path: Path) -> None:
    source = _mv_game(tmp_path / "source")
    runtime = _runtime(tmp_path / "nwjs")
    output = tmp_path / "built"

    class FakeRuntimeManager:
        def __init__(self) -> None:
            self.requested: str | None = None

        def ensure_nwjs(self, version: str, *, progress=None) -> Path:
            self.requested = version
            if progress:
                progress("fake runtime resolved")
            return runtime

    manager = FakeRuntimeManager()
    messages: list[str] = []

    result = build_game(
        source,
        runtime_manager=manager,
        runtime_version="0.117.0",
        output=output,
        progress=messages.append,
    )

    assert result.success
    assert manager.requested == "0.117.0"
    assert messages == ["fake runtime resolved"]
    assert result.runtime_path == runtime


def test_builds_directly_from_zip_input(tmp_path: Path) -> None:
    source_tree = _mv_game(tmp_path / "zip-source")
    runtime = _runtime(tmp_path / "nwjs")
    archive = tmp_path / "jailbreak.zip"

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in source_tree.rglob("*"):
            if path.is_file():
                zipped.write(path, path.relative_to(source_tree))

    output = tmp_path / "jailbreak-frame"
    messages: list[str] = []
    result = build_game(
        archive,
        runtime=runtime,
        output=output,
        progress=messages.append,
    )

    assert result.success
    assert result.source_path == archive
    assert (output / "www/js/rpg_core.js").is_file()
    assert (output / "launch.sh").is_file()
    assert any("Extracted ZIP input" in message for message in messages)
    assert any("ZIP input" in warning for warning in result.warnings)

    package = json.loads((output / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == "rpgmframe-jailbreak"


def test_default_zip_output_drops_zip_suffix(tmp_path: Path) -> None:
    archive = tmp_path / "game.zip"

    from rpgmframe.builder import default_output_path

    assert default_output_path(archive) == tmp_path / "game-frame"


def test_preserves_mv_package_root_companions_without_windows_runtime(
    tmp_path: Path,
) -> None:
    source = _mv_game(tmp_path / "source")
    wrapper = source / "jailbreak_win"
    _write(wrapper / "data/Quests.yaml", "quests: {}\n")
    _write(wrapper / "steam_appid.txt", "123456\n")
    _write(wrapper / "Game.exe", "windows runtime")
    _write(wrapper / "nw.dll", "windows runtime")
    _write(wrapper / "nw_100_percent.pak", "windows runtime")
    _write(wrapper / "nw_200_percent.pak", "windows runtime")

    runtime = _runtime(tmp_path / "nwjs")
    output = tmp_path / "built"
    result = build_game(source, runtime=runtime, output=output)

    assert (output / "data/Quests.yaml").is_file()
    assert (output / "steam_appid.txt").read_text(encoding="utf-8") == "123456\n"
    assert not (output / "Game.exe").exists()
    assert not (output / "nw.dll").exists()
    assert not (output / "nw_100_percent.pak").exists()
    assert not (output / "nw_200_percent.pak").exists()
    assert any("package-root companion" in warning for warning in result.warnings)


def test_warns_about_case_insensitive_collisions(tmp_path: Path) -> None:
    source = _mv_game(tmp_path / "source")
    wrapper = source / "jailbreak_win"
    _write(wrapper / "www/img/pictures/Foo.png", "upper")
    _write(wrapper / "www/img/pictures/foo.png", "lower")

    runtime = _runtime(tmp_path / "nwjs")
    result = build_game(source, runtime=runtime, output=tmp_path / "built")

    assert any("Case-insensitive path collisions" in warning for warning in result.warnings)


def test_fpsmeter_repair_is_conservative(tmp_path: Path) -> None:
    source = _mv_game(tmp_path / "source")
    wrapper = source / "jailbreak_win"

    _write(
        wrapper / "www/js/rpg_core.js",
        'Utils.RPGMAKER_VERSION = "1.6.1";\n',
    )

    runtime = _runtime(tmp_path / "nwjs")
    output = tmp_path / "built"
    result = build_game(source, runtime=runtime, output=output)

    index_html = (output / "www/index.html").read_text(encoding="utf-8")
    assert "js/libs/fpsmeter.js" not in index_html
    assert not any("fpsmeter.js" in warning for warning in result.warnings)


def test_compat_shim_guards_package_scope_and_multiple_io_paths(
    tmp_path: Path,
) -> None:
    source = _mv_game(tmp_path / "source")
    runtime = _runtime(tmp_path / "nwjs")
    output = tmp_path / "built"

    build_game(source, runtime=runtime, output=output)

    shim = (output / "www/js/rpgmframe-compat.js").read_text(encoding="utf-8")
    assert "isInsidePackage" in shim
    assert "readFileSync" in shim
    assert "fs.promises" in shim
    assert "XMLHttpRequest.prototype.open" in shim
    assert "window.fetch" in shim
    assert "HTMLImageElement" in shim
    assert "matches.length !== 1" in shim


def test_case_compatibility_does_not_rename_source_assets(tmp_path: Path) -> None:
    source = _mv_game(tmp_path / "source")
    wrapper = source / "jailbreak_win"
    _write(wrapper / "www/img/pictures/leaf.png", "leaf")

    runtime = _runtime(tmp_path / "nwjs")
    output = tmp_path / "built"
    build_game(source, runtime=runtime, output=output)

    assert (output / "www/img/pictures/leaf.png").is_file()
    assert not (output / "www/img/pictures/Leaf.png").exists()


def test_repairs_old_mv_negative_skipcount_freeze_bug(tmp_path: Path) -> None:
    source = _mv_game(tmp_path / "source")
    wrapper = source / "jailbreak_win"
    core = wrapper / "www/js/rpg_core.js"
    core.write_text(
        core.read_text(encoding="utf-8")
        + "\nif (this._skipCount === 0) {\n    this._skipCount = 0;\n}\n",
        encoding="utf-8",
    )

    runtime = _runtime(tmp_path / "nwjs")
    output = tmp_path / "built"
    result = build_game(source, runtime=runtime, output=output)

    built_core = (output / "www/js/rpg_core.js").read_text(encoding="utf-8")
    assert "if (this._skipCount <= 0) {" in built_core
    assert "if (this._skipCount === 0) {" not in built_core
    assert any("render-freeze fix" in warning for warning in result.warnings)


def test_does_not_rewrite_mv_skipcount_when_already_fixed(tmp_path: Path) -> None:
    source = _mv_game(tmp_path / "source")
    wrapper = source / "jailbreak_win"
    core = wrapper / "www/js/rpg_core.js"
    core.write_text(
        core.read_text(encoding="utf-8")
        + "\nif (this._skipCount <= 0) {\n    this._skipCount = 0;\n}\n",
        encoding="utf-8",
    )

    runtime = _runtime(tmp_path / "nwjs")
    output = tmp_path / "built"
    result = build_game(source, runtime=runtime, output=output)

    built_core = (output / "www/js/rpg_core.js").read_text(encoding="utf-8")
    assert built_core.count("if (this._skipCount <= 0) {") == 1
    assert not any("render-freeze fix" in warning for warning in result.warnings)


def test_builds_rpg_maker_xp_with_arm64_mkxpz(tmp_path: Path) -> None:
    source = tmp_path / "xp"
    _write(
        source / "To the Moon.ini",
        "[Game]\n"
        "Library=RGSS104E.dll\n"
        "Scripts=Data\\Scripts.rxdata\n"
        "Title=To the Moon\n",
    )
    _write(source / "To the Moon.rgssad", "encrypted fixture")
    _write(source / "Audio/BGM/theme.ogg", "audio")

    runtime = tmp_path / "mkxpz"
    _write_elf(runtime / "mkxp-z.aarch64", 183)
    _write(runtime / "LICENSE.txt", "GPL")
    _write(runtime / "stdlib/aarch64-linux/rbconfig.rb", "fixture")
    _write(runtime / "scripts/preload/mkxp_wrap.rb", "fixture")

    output = tmp_path / "built"
    result = build_game(source, runtime=runtime, output=output)

    assert result.success
    assert result.engine is EngineVariant.XP
    assert result.runtime_architecture == "aarch64"
    assert (output / "mkxp-z.aarch64").is_file()
    assert (output / "game/To the Moon.rgssad").is_file()
    assert (output / "game/To the Moon.ini").is_file()
    assert (output / "launch.sh").is_file()

    config = json.loads((output / "game/mkxp.json").read_text(encoding="utf-8"))
    assert config["gameFolder"] == "."
    assert config["rgssVersion"] == 1
    assert config["execName"] == "To the Moon"
    assert config["pathCache"] is True

    launcher = (output / "launch.sh").read_text(encoding="utf-8")
    assert "plasmashell" in launcher
    assert 'export SRCDIR="$ROOT/game"' in launcher
    assert 'SDL_VIDEO_HIGHDPI_DISABLED=' in launcher
    assert 'exec "$ROOT/mkxp-z.aarch64" "$@"' in launcher


def test_builds_godot_pck_with_supplied_arm64_runtime(tmp_path: Path) -> None:
    from rpgmframe.godot import PCK_MAGIC

    source = tmp_path / "godot"
    source.mkdir()
    pck = struct.pack("<IIIII", PCK_MAGIC, 3, 4, 3, 0) + b"fixture"
    (source / "Tiny Game.pck").write_bytes(pck)
    (source / "Tiny Game.exe").write_bytes(b"windows binary")

    runtime = tmp_path / "godot-runtime"
    _write_elf(runtime / "godot.arm64", 183)

    output = tmp_path / "built"
    result = build_game(source, runtime=runtime, output=output)

    assert result.success
    assert result.engine is EngineVariant.GODOT
    assert result.engine_version == "4.3.0"
    assert result.runtime_architecture == "aarch64"
    assert (output / "godot.arm64").is_file()
    assert (output / "game/Tiny Game.pck").read_bytes() == pck
    assert not (output / "game/Tiny Game.exe").exists()

    launcher = (output / "launch.sh").read_text(encoding="utf-8")
    assert "--main-pack" in launcher
    assert "Tiny Game.pck" in launcher
    assert "plasmashell" in launcher


def test_builds_embedded_godot_export_by_extracting_pck(tmp_path: Path) -> None:
    from rpgmframe.godot import PCK_MAGIC

    source = tmp_path / "godot-embedded"
    source.mkdir()
    pck = struct.pack("<IIIII", PCK_MAGIC, 3, 4, 2, 2) + b"payload"
    exe = source / "Embedded Game.exe"
    exe.write_bytes(
        b"MZ" + b"\0" * 62 + pck + struct.pack("<QI", len(pck), PCK_MAGIC)
    )

    runtime = tmp_path / "godot-runtime"
    _write_elf(runtime / "godot.arm64", 183)

    output = tmp_path / "built"
    result = build_game(source, runtime=runtime, output=output)

    assert result.engine is EngineVariant.GODOT
    assert (output / "game/Embedded Game.pck").read_bytes() == pck
    assert not (output / "game/Embedded Game.exe").exists()



def test_migrates_legacy_mkxp_distribution_settings_and_preloads(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy-mkxp"
    _write(
        source / "Legacy.ini",
        "[Game]\n"
        "Library=RGSS104E.dll\n"
        "Scripts=Data\\Scripts.rxdata\n"
        "Title=Legacy Game\n",
    )
    _write(source / "Legacy.rgssad", "encrypted fixture")
    _write(
        source / "mkxp.conf",
        "fullscreen=true\n"
        "smoothScaling=false\n"
        "dataPathOrg=Example Studio\n"
        "dataPathApp=/\n"
        "execName=Legacy\n"
        "RTP=lang.dat\n"
        "fontSub=Arial>Open Sans\n"
        "fontSub=Times New Roman>Liberation Serif\n",
    )
    _write(source / "mkxp-console.exe", "old Windows runtime")
    _write(source / "preload/ruby18_comp.rb", "# compatibility")
    _write(source / "preload/win32_wrap.rb", "# compatibility")

    runtime = tmp_path / "mkxpz"
    _write_elf(runtime / "mkxp-z.aarch64", 183)
    _write(runtime / "LICENSE.txt", "GPL")
    _write(runtime / "stdlib/aarch64-linux/rbconfig.rb", "fixture")
    _write(runtime / "scripts/preload/ruby_classic_wrap.rb", "# wrapper")
    _write(runtime / "scripts/preload/mkxp_wrap.rb", "# wrapper")
    _write(runtime / "scripts/preload/win32_wrap.rb", "# wrapper")

    output = tmp_path / "built"
    result = build_game(source, runtime=runtime, output=output)

    config = json.loads((output / "game/mkxp.json").read_text(encoding="utf-8"))
    assert config["gameFolder"] == "."
    assert config["fullscreen"] is True
    assert config["smoothScaling"] == 0
    assert config["dataPathOrg"] == "Example Studio"
    assert config["dataPathApp"] == "/"
    assert config["execName"] == "Legacy"
    assert config["RTP"] == ["lang.dat"]
    assert config["fontSub"] == [
        "Arial>Open Sans",
        "Times New Roman>Liberation Serif",
    ]
    assert config["preloadScript"] == [
        "../scripts/preload/ruby_classic_wrap.rb",
        "../scripts/preload/mkxp_wrap.rb",
        "preload/ruby18_comp.rb",
        "preload/win32_wrap.rb",
    ]
    assert any("legacy mkxp.conf" in warning for warning in result.warnings)


def test_mkxp_launcher_disables_hidpi_fractional_pointer_scaling(tmp_path: Path) -> None:
    source = tmp_path / "xp"
    _write(
        source / "Game.ini",
        "[Game]\nLibrary=RGSS104E.dll\nScripts=Data\\Scripts.rxdata\n",
    )
    _write(source / "Data/Scripts.rxdata", "fixture")

    runtime = tmp_path / "mkxpz"
    _write_elf(runtime / "mkxp-z.aarch64", 183)
    _write(runtime / "LICENSE.txt", "GPL")
    _write(runtime / "stdlib/aarch64-linux/rbconfig.rb", "fixture")
    _write(runtime / "scripts/preload/ruby_classic_wrap.rb", "# wrapper")
    _write(runtime / "scripts/preload/mkxp_wrap.rb", "# wrapper")
    _write(runtime / "scripts/preload/win32_wrap.rb", "# wrapper")

    output = tmp_path / "built"
    build_game(source, runtime=runtime, output=output)

    launcher = (output / "launch.sh").read_text(encoding="utf-8")
    assert 'export SRCDIR="$ROOT/game"' in launcher
    assert 'SDL_VIDEO_HIGHDPI_DISABLED' in launcher
