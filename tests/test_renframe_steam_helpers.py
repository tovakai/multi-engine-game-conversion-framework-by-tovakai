from pathlib import Path

from renpy_arm.convert import patch_launcher_sh, write_steam_helpers


def test_steam_wrapper_does_not_inject_basedir_argument(tmp_path: Path) -> None:
    launcher = tmp_path / "Sample Game.sh"
    launcher.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    write_steam_helpers(tmp_path, "Sample Game", "8.5.3", launcher)

    wrapper = (tmp_path / "launch-steam.sh").read_text(encoding="utf-8")
    assert 'chmod +x "$GAME_DIR/Sample Game.sh"' in wrapper
    assert 'exec "$GAME_DIR/Sample Game.sh" "$@"' in wrapper
    assert 'exec "$GAME_DIR/Sample Game.sh" "$GAME_DIR" "$@"' not in wrapper


def test_frame_diagnostic_helper_is_written(tmp_path: Path) -> None:
    launcher = tmp_path / "Sample Game.sh"
    launcher.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    write_steam_helpers(tmp_path, "Sample Game", "8.5.3", launcher)

    diag = (tmp_path / "diagnose-frame.sh").read_text(encoding="utf-8")
    assert 'if [[ "${1:-}" == "--launch" ]]; then' in diag
    assert 'bash -x "$GAME_DIR/launch-steam.sh"' in diag
    assert "librenpython dependencies" in diag


def test_launcher_crlf_is_normalized_even_if_arm_mapping_exists(tmp_path: Path) -> None:
    launcher = tmp_path / "Legacy.sh"
    launcher.write_bytes(
        b"#!/bin/sh\r\n"
        b"case \"$RENPY_PLATFORM\" in\r\n"
        b"  *-aarch64|*-arm64)\r\n"
        b"    RENPY_PLATFORM=\"linux-aarch64\"\r\n"
        b"    ;;\r\n"
        b"esac\r\n"
    )

    patch_launcher_sh(launcher)

    data = launcher.read_bytes()
    assert b"\r" not in data
    assert data.startswith(b"#!/bin/sh\n")


def test_steam_wrapper_discovers_frametop_x11_environment(tmp_path: Path) -> None:
    launcher = tmp_path / "Sample Game.sh"
    launcher.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    write_steam_helpers(tmp_path, "Sample Game", "8.5.3", launcher)

    wrapper = (tmp_path / "launch-steam.sh").read_text(encoding="utf-8")
    assert 'FRAME_RUNTIME_DIR="/run/user/$(id -u)/frametop"' in wrapper
    assert 'export XDG_RUNTIME_DIR="$FRAME_RUNTIME_DIR"' in wrapper
    assert 'export DISPLAY=":2"' in wrapper
    assert 'export SDL_VIDEODRIVER="x11"' in wrapper
    assert '"$FRAME_RUNTIME_DIR"/xauth_*' in wrapper
    assert 'export XAUTHORITY="$XAUTH_FILE"' in wrapper
    assert 'exec "$GAME_DIR/Sample Game.sh" "$@"' in wrapper


def test_add_to_steam_registers_direct_launcher_not_desktop_file(tmp_path: Path) -> None:
    launcher = tmp_path / "Sample Game.sh"
    launcher.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    write_steam_helpers(tmp_path, "Sample Game", "8.5.3", launcher)

    helper = (tmp_path / "add-to-steam.sh").read_text(encoding="utf-8")
    assert 'steamos-add-to-steam "$LAUNCH"' in helper
    assert 'steamos-add-to-steam "$DESKTOP"' not in helper
    assert 'safe=""))\' "$LAUNCH")' in helper
    assert 'safe=""))\' "$DESKTOP")' not in helper


def test_steam_helpers_write_quiet_conversion_attribution(tmp_path: Path) -> None:
    launcher = tmp_path / "Sample Game.sh"
    launcher.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    write_steam_helpers(tmp_path, "Sample Game", "8.5.3", launcher)

    metadata = (tmp_path / ".renframe" / "conversion.txt").read_text(encoding="utf-8")
    assert "Converted to Linux ARM64 with RenFrame." in metadata
    assert "RenFrame by Zum Glitchbrain." in metadata
    assert "Runtime: Ren'Py 8.5.3" in metadata

    wrapper = (tmp_path / "launch-steam.sh").read_text(encoding="utf-8")
    assert "# RenFrame by Zum Glitchbrain." in wrapper


def test_legacy_launcher_maps_arm_to_python_prefixed_runtime(tmp_path: Path) -> None:
    launcher = tmp_path / "Legacy.sh"
    launcher.write_text(
        '#!/bin/sh\n'
        'if [ -z "$RENPY_PLATFORM" ] ; then\n'
        '    RENPY_PLATFORM="$(uname -s)-$(uname -m)"\n'
        '    case "$RENPY_PLATFORM" in\n'
        '        Linux-*)\n'
        '            RENPY_PLATFORM="linux-$(uname -m)"\n'
        '            ;;\n'
        '    esac\n'
        'fi\n'
        'LIB="$ROOT/lib/$RENPY_PLATFORM"\n',
        encoding="utf-8",
    )

    patch_launcher_sh(launcher, python_tag="py2")

    text = launcher.read_text(encoding="utf-8")
    assert 'RENPY_PLATFORM="py2-linux-aarch64"' in text


def test_legacy_launcher_repairs_existing_plain_arm_mapping(tmp_path: Path) -> None:
    launcher = tmp_path / "Legacy.sh"
    launcher.write_text(
        '#!/bin/sh\n'
        'case "$RENPY_PLATFORM" in\n'
        '    *-aarch64|*-arm64)\n'
        '        RENPY_PLATFORM="linux-aarch64"\n'
        '        ;;\n'
        '    Linux-*)\n'
        '        RENPY_PLATFORM="linux-$(uname -m)"\n'
        '        ;;\n'
        'esac\n'
        'LIB="$ROOT/lib/$RENPY_PLATFORM"\n',
        encoding="utf-8",
    )

    patch_launcher_sh(launcher, python_tag="py2")

    text = launcher.read_text(encoding="utf-8")
    assert 'RENPY_PLATFORM="py2-linux-aarch64"' in text
    assert 'RENPY_PLATFORM="linux-aarch64"' not in text


def test_modern_launcher_keeps_unprefixed_platform_mapping(tmp_path: Path) -> None:
    launcher = tmp_path / "Modern.sh"
    launcher.write_text(
        '#!/bin/sh\n'
        'case "$RENPY_PLATFORM" in\n'
        '    Linux-*)\n'
        '        RENPY_PLATFORM="linux-$(uname -m)"\n'
        '        ;;\n'
        'esac\n'
        'LIB="$ROOT/lib/$PYTHON-$RENPY_PLATFORM"\n',
        encoding="utf-8",
    )

    patch_launcher_sh(launcher, python_tag="py3")

    text = launcher.read_text(encoding="utf-8")
    assert 'RENPY_PLATFORM="linux-aarch64"' in text
    assert 'RENPY_PLATFORM="py3-linux-aarch64"' not in text
