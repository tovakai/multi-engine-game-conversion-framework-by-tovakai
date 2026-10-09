from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from rpgmframe.godot_custom_runtime import (
    RECIPE_ID,
    CustomGodotRuntimeManager,
    _WORKER_SCRIPT,
    automatic_recipe_for,
)


def _write_elf(path: Path, machine: int = 183) -> None:
    header = bytearray(20)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[18:20] = machine.to_bytes(2, "little")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header)


def test_automatic_recipe_is_narrow() -> None:
    assert (
        automatic_recipe_for(
            "3.7.0",
            custom_build=True,
            godotsteam=True,
        )
        == RECIPE_ID
    )
    assert (
        automatic_recipe_for(
            "3.7.0",
            custom_build=True,
            godotsteam=False,
        )
        is None
    )
    assert (
        automatic_recipe_for(
            "4.3.0",
            custom_build=True,
            godotsteam=True,
        )
        is None
    )
    assert (
        automatic_recipe_for(
            "3.7.0",
            custom_build=False,
            godotsteam=True,
        )
        is None
    )


def test_cached_runtime_is_reused_without_building(tmp_path: Path) -> None:
    manager = CustomGodotRuntimeManager(
        cache_dir=tmp_path / "cache",
        work_dir=tmp_path / "work",
        steam_api=tmp_path / "missing-steam-api.so",
    )
    runtime = manager.runtime_path()
    runtime.mkdir(parents=True)
    _write_elf(runtime / "godot.arm64")
    _write_elf(runtime / "libsteam_api.so")
    (runtime / "runtime.json").write_text(
        json.dumps({"recipe_id": RECIPE_ID}),
        encoding="utf-8",
    )

    messages: list[str] = []
    resolved = manager.ensure_runtime(progress=messages.append)

    assert resolved == runtime
    assert any("cached custom Godot" in message for message in messages)


def test_cached_runtime_rejects_wrong_recipe(tmp_path: Path) -> None:
    manager = CustomGodotRuntimeManager(
        cache_dir=tmp_path / "cache",
        work_dir=tmp_path / "work",
    )
    runtime = manager.runtime_path()
    runtime.mkdir(parents=True)
    _write_elf(runtime / "godot.arm64")
    _write_elf(runtime / "libsteam_api.so")
    (runtime / "runtime.json").write_text(
        json.dumps({"recipe_id": "wrong-recipe"}),
        encoding="utf-8",
    )

    assert manager._validate_runtime(runtime) is False


def test_worker_script_contains_proven_compatibility_stack() -> None:
    assert "a117d512" not in _WORKER_SCRIPT  # refs are injected through environment
    assert "steamworks_sdk_162" in _WORKER_SCRIPT
    assert "GodotSteam 3.30" in _WORKER_SCRIPT
    assert "CanvasItem cast fix" in _WORKER_SCRIPT
    assert "arch=arm64" in _WORKER_SCRIPT
    assert "lto=none" in _WORKER_SCRIPT


def test_worker_script_has_valid_bash_syntax() -> None:
    bash = shutil.which("bash")
    if bash is None:
        return
    subprocess.run(
        [bash, "-n"],
        input=_WORKER_SCRIPT.encode(),
        check=True,
    )
