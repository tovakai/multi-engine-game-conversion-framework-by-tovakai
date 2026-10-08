from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from megcfbt import router
from megcfbt.models import UnifiedInspection


def test_renpy_router_delegates_automatic_runtime_to_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "game"
    (source / "game").mkdir(parents=True)
    (source / "game/script.rpy").write_text("label start:\n    pass\n")

    inspection = UnifiedInspection(
        source_path=source,
        backend="renframe",
        engine="renpy",
        engine_label="Ren'Py",
        engine_version="8.5.3",
        game_name="Synthetic",
        compatibility="LIKELY_COMPATIBLE",
        confidence="high",
        runtime_kind="official Ren'Py 8.5.3 sdkarm platform (automatic)",
        buildable=True,
    )
    monkeypatch.setattr(router, "inspect_source", lambda path: inspection)
    monkeypatch.setattr(router, "_inspect_prepared", lambda root: inspection)

    seen = {}

    def fake_build(source_path, **kwargs):
        seen["runtime"] = kwargs["runtime"]
        seen["progress"] = kwargs["progress"]
        out = Path(kwargs["output"])
        out.mkdir(parents=True)
        launcher = out / "launch.sh"
        launcher.write_text("#!/bin/sh\n")
        return SimpleNamespace(
            launcher_path=launcher,
            warnings=["automatic backend"],
            display_name="Synthetic",
            game_name="Synthetic",
            source_version="8.5.3",
        )

    monkeypatch.setattr(router, "build_renpy_game", fake_build)

    progress = lambda message: None
    result = router.build_source(source, archive=False, progress=progress)

    assert seen["runtime"] is None
    assert seen["progress"] is progress
    assert result.engine == "renpy"
    assert result.engine_version == "8.5.3"
    assert "automatic backend" in result.warnings


def test_renpy_router_passes_manual_runtime_override_through(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "game"
    (source / "game").mkdir(parents=True)
    (source / "game/script.rpy").write_text("label start:\n    pass\n")
    manual = tmp_path / "manual-runtime"
    manual.mkdir()

    inspection = UnifiedInspection(
        source_path=source,
        backend="renframe",
        engine="renpy",
        engine_label="Ren'Py",
        engine_version="8.5.3",
        game_name="Synthetic",
        compatibility="LIKELY_COMPATIBLE",
        confidence="high",
        runtime_kind="official Ren'Py 8.5.3 sdkarm platform (automatic)",
        buildable=True,
    )
    monkeypatch.setattr(router, "inspect_source", lambda path: inspection)
    monkeypatch.setattr(router, "_inspect_prepared", lambda root: inspection)

    seen = {}

    def fake_build(source_path, **kwargs):
        seen["runtime"] = Path(kwargs["runtime"])
        out = Path(kwargs["output"])
        out.mkdir(parents=True)
        launcher = out / "Synthetic.sh"
        launcher.write_text("#!/bin/sh\n")
        return SimpleNamespace(
            launcher_path=launcher,
            warnings=[],
            display_name="Synthetic",
            game_name="Synthetic",
            source_version="8.5.3",
        )

    monkeypatch.setattr(router, "build_renpy_game", fake_build)

    router.build_source(source, archive=False, renpy_runtime=manual)

    assert seen["runtime"] == manual



def test_renpy_router_forwards_experimental_fallback_approval(
    tmp_path: Path, monkeypatch,
) -> None:
    source = tmp_path / "legacy"
    (source / "game").mkdir(parents=True)
    (source / "game/script.rpy").write_text("label start:\n    pass\n")

    inspection = UnifiedInspection(
        source_path=source,
        backend="renframe",
        engine="renpy",
        engine_label="Ren'Py",
        engine_version="7.4.11",
        game_name="Legacy",
        compatibility="NEEDS_TESTING",
        confidence="high",
        runtime_kind="experimental Ren'Py 7.5.0 Python 2 ARM64 fallback",
        buildable=True,
        renpy_generation=7,
    )
    monkeypatch.setattr(router, "inspect_source", lambda path: inspection)
    monkeypatch.setattr(router, "_inspect_prepared", lambda root: inspection)

    captured = []

    def fake_build(source_path, **kwargs):
        captured.append(kwargs)
        out = Path(kwargs["output"])
        out.mkdir()
        launcher = out / "launch.sh"
        launcher.write_text("#!/bin/sh\n")
        return SimpleNamespace(
            launcher_path=launcher,
            warnings=["EXPERIMENTAL: Ren'Py 7.5.0 fallback, gameplay unverified"],
            display_name="Legacy",
            game_name="Legacy",
            source_version="7.4.11",
        )

    monkeypatch.setattr(router, "build_renpy_game", fake_build)

    result = router.build_source(
        source, archive=False, renpy_legacy_arm64_fallback=True
    )
    assert captured[0]["runtime"] is None
    assert captured[0]["legacy_arm64_fallback"] is True
    assert "EXPERIMENTAL" in result.warnings[0]
    assert result.engine_version == "7.4.11"
