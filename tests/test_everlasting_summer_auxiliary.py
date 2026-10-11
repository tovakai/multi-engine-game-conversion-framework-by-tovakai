"""Regression checks for Everlasting Summer's bundled Workshop utilities."""

from pathlib import Path

from renframe.builder import _validate_source_inspection
from renframe.models import Compatibility, GameInspection, NativeDependency, Ownership
from renframe.scanner import (
    classify_compatibility,
    game_owned_native_problems,
    scan_native_dependencies,
)


def _dep(path: str) -> NativeDependency:
    suffix = path.lower().rsplit(".", 1)[-1]
    kind = "windows_executable" if suffix == "exe" else "windows_dll"
    return NativeDependency(
        path=Path(path),
        kind=kind,
        architecture="windows",
        ownership=Ownership.GAME,
    )


def _verdict(deps):
    return classify_compatibility(
        is_renpy=True,
        renpy_version="8.0.1",
        generation=8,
        native_dependencies=deps,
        warnings=[],
    )


def test_stock_es_workshop_uploader_and_editor_are_nonblocking(tmp_path):
    root = tmp_path / "Everlasting Summer"
    (root / "game").mkdir(parents=True)
    binaries = [
        "game/mods/ES_Content_Uploader.exe",
        "game/mods/Qt5Core.dll",
        "game/mods/Qt5Gui.dll",
        "game/mods/Qt5Widgets.dll",
        "game/mods/steam_api.dll",
        "game/mods/vc_redist.x86.exe",
        "game/mods/platforms/qwindows.dll",
        "game/mods/styles/qwindowsvistastyle.dll",
        "game/mods/imageformats/qwebp.dll",
        "game/mods/editor/ESCU_BBCode_Editor.exe",
        "game/mods/editor/Qt5WebEngineCore.dll",
        "game/mods/editor/QtWebEngineProcess.exe",
        "game/mods/editor/bearer/qgenericbearer.dll",
        "game/mods/editor/d3dcompiler_47.dll",
        # Remaining stock Qt editor DLLs observed in a fresh Steam installation.
        "game/mods/editor/iconengines/qsvgicon.dll",
        "game/mods/editor/imageformats/qgif.dll",
        "game/mods/editor/imageformats/qicns.dll",
        "game/mods/editor/imageformats/qico.dll",
        "game/mods/editor/imageformats/qjpeg.dll",
        "game/mods/editor/imageformats/qsvg.dll",
        "game/mods/editor/imageformats/qtga.dll",
        "game/mods/editor/imageformats/qtiff.dll",
        "game/mods/editor/imageformats/qwbmp.dll",
        "game/mods/editor/imageformats/qwebp.dll",
        "game/mods/editor/libEGL.dll",
        "game/mods/editor/libGLESv2.dll",
        "game/mods/editor/platforms/qwindows.dll",
        "game/mods/editor/position/qtposition_positionpoll.dll",
        "game/mods/editor/position/qtposition_serialnmea.dll",
        "game/mods/editor/position/qtposition_winrt.dll",
        "game/mods/editor/printsupport/windowsprintersupport.dll",
        "game/mods/editor/styles/qwindowsvistastyle.dll",
    ]
    for rel in binaries:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"MZ")

    deps = scan_native_dependencies(root)
    assert len(deps) == len(binaries)
    assert game_owned_native_problems(deps) == []
    status, issues = _verdict(deps)
    assert status == Compatibility.NEEDS_TESTING
    assert any("Workshop uploader/editor" in issue for issue in issues)

    # No hard blocker means the ordinary (still cautious) build route can run.
    inspection = GameInspection(
        source_path=root,
        is_renpy=True,
        compatibility=status,
        potential_issues=issues,
    )
    warnings = _validate_source_inspection(
        inspection,
        allow_version_mismatch=False,
    )
    assert any("NEEDS_TESTING" in warning for warning in warnings)


def test_unknown_mod_native_code_still_blocks_with_uploader_present():
    deps = [
        _dep("game/mods/ES_Content_Uploader.exe"),
        _dep("game/mods/custom_mod/required.dll"),
        _dep("game/mods/editor/custom_plugin.dll"),
        _dep("game/mods/editor/imageformats/custom_codec.dll"),
        _dep("game/mods/editor/position/custom_provider.dll"),
        _dep("game/native/required.pyd"),
    ]
    problems = game_owned_native_problems(deps)
    assert {p.path.as_posix() for p in problems} == {
        "game/mods/custom_mod/required.dll",
        "game/mods/editor/custom_plugin.dll",
        "game/mods/editor/imageformats/custom_codec.dll",
        "game/mods/editor/position/custom_provider.dll",
        "game/native/required.pyd",
    }
    assert _verdict(deps)[0] == Compatibility.INCOMPATIBLE_NATIVE_CODE


def test_uploader_markers_required_to_exempt_qt_components():
    assert [d.path for d in game_owned_native_problems([
        _dep("game/mods/Qt5Core.dll")
    ])] == [Path("game/mods/Qt5Core.dll")]

    # The editor needs its own marker: an unrelated editor folder stays blocked.
    deps = [
        _dep("game/mods/ES_Content_Uploader.exe"),
        _dep("game/mods/editor/Qt5Core.dll"),
    ]
    assert [d.path for d in game_owned_native_problems(deps)] == [
        Path("game/mods/editor/Qt5Core.dll")
    ]


def test_case_insensitive_windows_paths_in_stock_uploader():
    deps = [
        _dep(r"GAME\MODS\es_CONTENT_uploader.EXE"),
        _dep(r"GAME\MODS\QT5CORE.DLL"),
    ]
    assert game_owned_native_problems(deps) == []


def test_windows_native_code_elsewhere_still_blocks():
    deps = [_dep("game/extensions/NativePlugin.dll")]
    assert game_owned_native_problems(deps) == deps
    assert _verdict(deps)[0] == Compatibility.INCOMPATIBLE_NATIVE_CODE
