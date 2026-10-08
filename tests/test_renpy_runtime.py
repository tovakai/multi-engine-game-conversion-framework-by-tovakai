from __future__ import annotations

import hashlib
import shutil
import subprocess
import struct
import tarfile
from pathlib import Path

import pytest

from renframe.builder import BuildError, build_game
from renframe.inspect_service import inspect_game
from renframe.runtime import (
    RuntimeDownloadError,
    RuntimeManager,
    _parse_sha256,
    normalize_release_version,
    experimental_arm64_fallback,
    requires_pre_sdkarm_override,
    python_tag_for_generation,
)


def _write_elf(path: Path, machine: int = 183) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[6] = 1
    struct.pack_into("<H", header, 16, 3)
    struct.pack_into("<H", header, 18, machine)
    path.write_bytes(header)


def _sdkarm_archive(path: Path, version: str = "8.5.3", tag: str = "py3") -> str:
    source = path.parent / "sdk-source"
    platform = source / f"renpy-{version}-sdk" / "lib" / f"{tag}-linux-aarch64"
    _write_elf(platform / "renpy")
    _write_elf(platform / "python")
    (platform / "payload.txt").write_text("arm runtime", encoding="utf-8")

    with tarfile.open(path, "w:bz2") as archive:
        archive.add(source / f"renpy-{version}-sdk", arcname=f"renpy-{version}-sdk")

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _renpy_game(root: Path, version: str = "8.5.3") -> Path:
    (root / "renpy").mkdir(parents=True)
    (root / "game").mkdir()
    (root / "lib/py3-linux-x86_64").mkdir(parents=True)
    (root / "renpy/__init__.py").write_text("# renpy\n", encoding="utf-8")
    (root / "renpy/versions.py").write_text(
        f'version = "{version}"\n',
        encoding="utf-8",
    )
    (root / "game/script.rpy").write_text(
        'label start:\n    "hello"\n',
        encoding="utf-8",
    )
    (root / "renpy.py").write_text("# launcher entry\n", encoding="utf-8")
    (root / "Game.sh").write_text(
        "#!/bin/sh\n"
        'UNAME="$(uname -s)-$(uname -m)"\n'
        'case "$UNAME" in\n'
        '    Linux-*)\n'
        '        RENPY_PLATFORM="linux-x86_64"\n'
        '        ;;\n'
        'esac\n'
        'exec "$RENPY_PLATFORM" "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    return root


def test_normalizes_exact_release_versions() -> None:
    assert normalize_release_version("8.5.3") == "8.5.3"
    assert normalize_release_version("8.5.3.26051504") == "8.5.3"
    with pytest.raises(RuntimeDownloadError):
        normalize_release_version("8.5")


def test_python_tag_tracks_renpy_generation() -> None:
    assert python_tag_for_generation(8) == "py3"
    assert python_tag_for_generation(7) == "py2"
    with pytest.raises(RuntimeDownloadError):
        python_tag_for_generation(6)


def test_checksum_parser_uses_sha256_section() -> None:
    filename = "renpy-8.5.3-sdkarm.tar.bz2"
    digest = "a" * 64
    text = (
        "-----BEGIN PGP SIGNED MESSAGE-----\n"
        "Hash: SHA512\n"
        "# md5\n"
        + ("b" * 32)
        + f" {filename}\n"
        "# sha256\n"
        + digest
        + f" {filename}\n"
    )
    assert _parse_sha256(text, filename) == digest


def test_runtime_manager_downloads_verifies_extracts_and_reuses_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "renpy-8.5.3-sdkarm.tar.bz2"
    digest = _sdkarm_archive(archive)
    manager = RuntimeManager(
        cache_dir=tmp_path / "cache",
        base_url="https://example.invalid/dl",
    )

    checksums = f"# sha256\n{digest} {archive.name}\n"
    monkeypatch.setattr(manager, "_read_url", lambda url: checksums)

    calls = {"download": 0}

    def fake_download(
        url: str,
        destination: Path,
        *,
        progress,
    ) -> None:
        calls["download"] += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, destination)

    monkeypatch.setattr(manager, "_download", fake_download)

    first = manager.ensure_platform("8.5.3", "py3")
    second = manager.ensure_platform("8.5.3", "py3")

    assert first == second
    assert calls["download"] == 1
    assert first.name == "py3-linux-aarch64"
    assert (first / "renpy").is_file()
    assert (first / "payload.txt").read_text(encoding="utf-8") == "arm runtime"



def _full_sdkarm_archive(path: Path) -> str:
    src = path.parent / "full-sdk-fixture" / "renpy-7.5.0-sdkarm"
    _fake_legacy_sdk(src)
    (src / "game").mkdir()
    (src / "game" / "example.rpy").write_text("label example:\n    pass\n")
    (src / "lib" / "py2-linux-x86_64").mkdir()
    (src / "lib" / "py2-linux-x86_64" / "python").write_text("x86")
    with tarfile.open(path, "w:bz2") as archive:
        archive.add(src, arcname="renpy-7.5.0-sdkarm")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_full_sdk_manager_extracts_matching_engine_and_arm64_and_reuses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "renpy-7.5.0-sdkarm.tar.bz2"
    digest = _full_sdkarm_archive(archive)
    manager = RuntimeManager(
        cache_dir=tmp_path / "cache", base_url="https://example.invalid/dl"
    )
    monkeypatch.setattr(
        manager, "_read_url", lambda url: f"# sha256\n{digest} {archive.name}\n"
    )
    count = []
    def fake_download(url, destination, *, progress):
        count.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, destination)
    monkeypatch.setattr(manager, "_download", fake_download)
    first = manager.ensure_full_sdk("7.5.0", "py2")
    second = manager.ensure_full_sdk("7.5.0", "py2")
    assert first == second
    assert len(count) == 1
    assert (first / "renpy/__init__.py").read_text() == "# Ren'Py 7.5 engine\n"
    assert (first / "renpy/versions.py").read_text() == 'version = "7.5.0"\n'
    assert (first / "renpy.py").is_file()
    assert (first / "renpy.sh").is_file()
    assert (first / "lib/py2-linux-aarch64/python").is_file()
    assert not (first / "lib/py2-linux-x86_64").exists()
    assert not (first / "game").exists()


def test_full_sdk_manager_rejects_wrong_python_generation(tmp_path: Path) -> None:
    manager = RuntimeManager(cache_dir=tmp_path / "cache")
    with pytest.raises(RuntimeDownloadError, match="only available"):
        manager.ensure_full_sdk("7.5.0", "py3")
    with pytest.raises(RuntimeDownloadError, match="only available"):
        manager.ensure_full_sdk("8.5.3", "py2")


def test_runtime_manager_refuses_versions_before_official_aarch64_support(
    tmp_path: Path,
) -> None:
    manager = RuntimeManager(cache_dir=tmp_path / "cache")
    with pytest.raises(RuntimeDownloadError, match="predates official Linux AArch64"):
        manager.ensure_platform("7.4.11", "py2")


def test_vc_version_source_recovers_exact_release(tmp_path: Path) -> None:
    root = _renpy_game(tmp_path / "game")
    (root / "renpy/versions.py").unlink()
    (root / "renpy/vc_version.py").write_text(
        "version = '8.5.3.26051504'\n",
        encoding="utf-8",
    )

    result = inspect_game(root)

    assert result.is_renpy
    assert result.renpy_version == "8.5.3"
    assert result.version_source == "renpy/vc_version.py"


def test_automatic_builder_grafts_arm_platform_and_patches_launcher(
    tmp_path: Path,
) -> None:
    source = _renpy_game(tmp_path / "Synthetic")
    # Shipped Ren'Py installations can contain bytecode-only stdlib modules.
    stdlib = source / "lib" / "python3.9"
    (stdlib / "encodings").mkdir(parents=True)
    (stdlib / "encodings" / "__init__.pyc").write_bytes(b"bytecode")
    (stdlib / "__future__.pyc").write_bytes(b"bytecode")
    cache = stdlib / "__pycache__"
    cache.mkdir()
    (cache / "abc.cpython-39.pyc").write_bytes(b"bytecode")
    platform = tmp_path / "runtime" / "8.5.3" / "py3-linux-aarch64"
    _write_elf(platform / "renpy")
    (platform / "runtime-marker.txt").write_text("arm", encoding="utf-8")

    class FakeManager:
        def platform_path(self, version: str, python_tag: str) -> Path:
            assert version == "8.5.3"
            assert python_tag == "py3"
            return platform

        def ensure_platform(
            self,
            version: str,
            python_tag: str,
            *,
            progress=None,
            force: bool = False,
        ) -> Path:
            assert force is False
            return self.platform_path(version, python_tag)

    output = tmp_path / "Synthetic-frame"
    result = build_game(
        source,
        output=output,
        runtime_manager=FakeManager(),
    )

    assert result.success
    assert result.runtime_version == "8.5.3"
    assert result.runtime_architecture == "aarch64"
    assert result.launcher_path == output / "launch.sh"

    # The distributed engine/game remains the source of truth.
    assert (output / "renpy/versions.py").read_text(encoding="utf-8") == (
        'version = "8.5.3"\n'
    )
    assert (output / "game/script.rpy").is_file()
    assert (output / "lib/py3-linux-x86_64").is_dir()
    assert (output / "lib/python3.9/encodings/__init__.pyc").read_bytes() == b"bytecode"
    assert (output / "lib/python3.9/__future__.pyc").read_bytes() == b"bytecode"
    assert (output / "lib/python3.9/__pycache__/abc.cpython-39.pyc").read_bytes() == b"bytecode"

    # Only the exact ARM platform slice is grafted in.
    assert (output / "lib/py3-linux-aarch64/renpy").is_file()
    assert (output / "lib/py3-linux-aarch64/Game").is_file()
    assert (output / "lib/py3-linux-aarch64/runtime-marker.txt").read_text(
        encoding="utf-8"
    ) == "arm"

    patched = (output / "Game.sh").read_text(encoding="utf-8")
    assert "*-aarch64|*-arm64)" in patched
    assert 'RENPY_PLATFORM="linux-aarch64"' in patched

    launcher = (output / "launch.sh").read_text(encoding="utf-8")
    assert 'export RENPY_PLATFORM="py3-linux-aarch64"' in launcher
    assert 'exec bash "$ROOT/Game.sh" "$ROOT" "$@"' in launcher
    assert 'chmod u+x "$binary"' in launcher
    assert 'RUNTIME_DIR="$ROOT/lib/py3-linux-aarch64"' in launcher


def test_automatic_builder_dry_run_does_not_download(tmp_path: Path) -> None:
    source = _renpy_game(tmp_path / "Synthetic")

    class NoDownloadManager:
        def platform_path(self, version: str, python_tag: str) -> Path:
            return tmp_path / "would-be-cache" / python_tag

        def ensure_platform(self, *args, **kwargs):
            raise AssertionError("dry-run must not download a runtime")

    output = tmp_path / "Synthetic-frame"
    result = build_game(
        source,
        output=output,
        dry_run=True,
        runtime_manager=NoDownloadManager(),
    )

    assert result.success
    assert not output.exists()



def _legacy_renpy_game(root: Path, version: str = "7.4.11") -> Path:
    game = _renpy_game(root, version=version)
    (game / "lib/py3-linux-x86_64").rename(game / "lib/py2-linux-x86_64")
    return game


def test_legacy_fallback_requires_verified_python2_and_74_version() -> None:
    assert experimental_arm64_fallback("7.4.11", 7) == "7.5.0"
    assert experimental_arm64_fallback("7.4.11.2266", 7) == "7.5.0"
    assert experimental_arm64_fallback("7.4.11", 8) is None
    assert experimental_arm64_fallback("7.4.11", None) is None
    assert experimental_arm64_fallback("7.3.5", 7) is None
    assert experimental_arm64_fallback("7.5.0", 7) is None
    assert experimental_arm64_fallback("8.0.1", 8) is None
    assert experimental_arm64_fallback("not a release", 7) is None
    assert requires_pre_sdkarm_override("7.4.11", 7)
    assert requires_pre_sdkarm_override("7.3.5", 7)
    assert not requires_pre_sdkarm_override("7.5.0", 7)
    assert not requires_pre_sdkarm_override("8.0.1", 8)


def test_legacy_renpy_build_requires_explicit_opt_in(tmp_path: Path) -> None:
    game = _legacy_renpy_game(tmp_path / "Legacy")
    inspection = inspect_game(game)
    assert inspection.renpy_version == "7.4.11"
    assert inspection.generation == 7
    manager = RuntimeManager(cache_dir=tmp_path / "runtime-cache")
    with pytest.raises(BuildError, match="predates official Linux AArch64"):
        build_game(game, output=tmp_path / "out", runtime_manager=manager)



def _fake_legacy_sdk(root: Path) -> Path:
    (root / "renpy").mkdir(parents=True)
    (root / "renpy/__init__.py").write_text("# Ren'Py 7.5 engine\n")
    (root / "renpy/versions.py").write_text('version = "7.5.0"\n')
    (root / "renpy.py").write_text("# Ren'Py entrypoint\n")
    (root / "LICENSE.txt").write_text("Synthetic license notice\n")
    (root / "lib/python2.7").mkdir(parents=True)
    (root / "lib/python2.7/site.py").write_text("# synthetic stdlib\n")
    launcher = root / "renpy.sh"
    launcher.write_text(
        '#!/bin/sh\n'
        'printf "full_sdk=%s game=%s\\n" "7.5.0" "$1"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    platform = root / "lib/py2-linux-aarch64"
    _write_elf(platform / "renpy")
    _write_elf(platform / "python")
    (platform / "runtime-marker.txt").write_text("official 7.5.0")
    return root


def test_opted_in_legacy_build_uses_matched_engine_and_preserves_original_game(
    tmp_path: Path,
) -> None:
    source = _legacy_renpy_game(tmp_path / "Legacy")
    (source / "game" / "unique_asset.txt").write_text("original ES game")
    sdk = _fake_legacy_sdk(tmp_path / "cache" / "full-sdk")

    class FakeManager:
        def full_sdk_path(self, version, tag):
            assert (version, tag) == ("7.5.0", "py2")
            return sdk

        def ensure_full_sdk(self, version, tag, *, progress=None):
            assert (version, tag) == ("7.5.0", "py2")
            return sdk

    out = tmp_path / "converted"
    logs = []
    result = build_game(
        source, output=out, runtime_manager=FakeManager(),
        legacy_arm64_fallback=True, progress=logs.append,
    )
    assert result.success
    assert result.source_version == "7.4.11"
    assert result.runtime_version == "7.5.0"
    assert result.runtime_architecture == "aarch64"
    assert any("EXPERIMENTAL" in warning for warning in result.warnings)
    assert any("matching official Ren'Py 7.5.0" in warning for warning in result.warnings)
    assert any("explicitly approved" in line for line in logs)
    assert (out / "lib/py2-linux-aarch64/renpy").is_file()
    assert (out / "lib/py2-linux-aarch64/runtime-marker.txt").read_text() == "official 7.5.0"
    assert (out / "renpy/versions.py").read_text() == 'version = "7.5.0"\n'
    assert (out / "game/unique_asset.txt").read_text() == "original ES game"
    assert not (out / "lib/py2-linux-x86_64").exists()
    assert not (source / "lib/py2-linux-aarch64").exists()
    assert (source / "renpy/versions.py").read_text() == 'version = "7.4.11"\n'
    assert result.launcher_path == out / "Game.sh"
    assert 'exec "$ROOT/renpy.sh"' in result.launcher_path.read_text()
    assert "sdk-compat" not in result.launcher_path.read_text()

def test_legacy_fallback_rejects_renpy8_and_wrong_7x_even_if_approved(tmp_path: Path):
    for version in ("8.5.3", "7.3.4", "7.3.6", "7.5.0"):
        source = _renpy_game(tmp_path / ("Game-" + version), version=version)
        if version.startswith("7."):
            (source / "lib/py3-linux-x86_64").rename(source / "lib/py2-linux-x86_64")
        with pytest.raises(BuildError, match="only available for identified Ren'Py 7.4"):
            build_game(
                source, output=tmp_path / ("out-" + version),
                legacy_arm64_fallback=True, dry_run=True,
            )


def test_legacy_fallback_rejects_manual_runtime_combination(tmp_path: Path):
    source = _legacy_renpy_game(tmp_path / "Legacy")
    runtime = tmp_path / "manual"
    runtime.mkdir()
    with pytest.raises(BuildError, match="either a manual"):
        build_game(
            source, output=tmp_path / "out", runtime=runtime,
            legacy_arm64_fallback=True, dry_run=True,
        )



def test_unified_inspection_preserves_legacy_python_generation_and_fallback_hint(
    tmp_path: Path,
) -> None:
    from megcfbt.router import inspect_source

    legacy = _legacy_renpy_game(tmp_path / "Legacy")
    detected = inspect_source(legacy)
    assert detected.renpy_generation == 7
    assert detected.engine_version == "7.4.11"
    assert "experimental Ren'Py 7.5.0 Python 2 ARM64" in detected.runtime_kind
    assert "requires user approval" in detected.runtime_kind

    old = _legacy_renpy_game(tmp_path / "Older", version="7.3.4")
    detected_old = inspect_source(old)
    assert detected_old.renpy_generation == 7
    assert "manual compatible ARM64" in detected_old.runtime_kind

    modern = _renpy_game(tmp_path / "Modern", version="8.5.3")
    detected_modern = inspect_source(modern)
    assert detected_modern.renpy_generation == 8
    assert "sdkarm platform (automatic)" in detected_modern.runtime_kind



@pytest.mark.skipif(shutil.which("bash") is None, reason="Needs Bash for POSIX launch test")
def test_legacy_full_engine_generated_launcher_executes_sdk_script(tmp_path: Path):
    """Regression: don't reuse a Ren'Py 7.4 launcher with Ren'Py 7.5 binaries."""
    source = _legacy_renpy_game(tmp_path / "Legacy")
    sdk = _fake_legacy_sdk(tmp_path / "sdk")

    class FakeManager:
        def full_sdk_path(self, version, tag):
            assert (version, tag) == ("7.5.0", "py2")
            return sdk

        def ensure_full_sdk(self, version, tag, *, progress=None):
            assert (version, tag) == ("7.5.0", "py2")
            return sdk

    out = tmp_path / "out"
    result = build_game(
        source, output=out, runtime_manager=FakeManager(),
        legacy_arm64_fallback=True,
    )
    completed = subprocess.run(
        ["bash", str(result.launcher_path)],
        cwd=out,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "full_sdk=7.5.0" in completed.stdout
    expected_path = out.as_posix()
    if out.drive:
        expected_path = "/" + out.drive[0].lower() + expected_path[2:]
    assert expected_path in completed.stdout
