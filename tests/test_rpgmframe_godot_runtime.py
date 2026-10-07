from __future__ import annotations

from pathlib import Path

from rpgmframe.godot_runtime import GodotRuntimeManager, _candidate_tags


def _write_elf(path: Path, machine: int = 183) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[6] = 1
    header[18:20] = machine.to_bytes(2, "little")
    path.write_bytes(header)


def test_zero_patch_prefers_godot_release_tag_without_dot_zero() -> None:
    assert _candidate_tags("4.3.0") == ["4.3-stable", "4.3.0-stable"]


def test_patch_release_uses_exact_tag() -> None:
    assert _candidate_tags("4.7.2") == ["4.7.2-stable"]


def test_reuses_cached_arm64_godot_runtime(tmp_path: Path) -> None:
    manager = GodotRuntimeManager(cache_dir=tmp_path / "cache")
    runtime = manager.runtime_path("4.3.0")
    _write_elf(runtime / "godot.arm64")

    messages: list[str] = []
    resolved = manager.ensure_godot("4.3.0", progress=messages.append)

    assert resolved == runtime
    assert any("Using cached Godot 4.3.0 ARM64" in message for message in messages)
