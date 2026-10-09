"""Synthetic, engine-generic 7.3.5 migration checks. No game assets."""
import hashlib
import json
import shutil
import tarfile
import zipfile
from types import SimpleNamespace

import pytest

from megcfbt import gui, router
from megcfbt.cli import main as unified_main
from renframe.cli import main as renframe_main
from renframe.builder import BuildError, build_game
from renframe.runtime import RuntimeDownloadError, RuntimeManager, experimental_arm64_fallback
from test_gui_renpy_fallback import app_for_inspection, synchronous_threads
from test_renpy_runtime import _legacy_renpy_game, _fake_legacy_sdk, _full_sdkarm_archive, _write_elf


@pytest.mark.parametrize("version,eligible", [
    ("7.3.5", True), ("7.3.4", False), ("7.3.6", False),
    ("7.4.11", True), ("6.99.12", False), ("7.5.0", False), ("8.3.7", False),
])
def test_exact_gate_and_download_free_dry_run(tmp_path, version, eligible):
    source = _legacy_renpy_game(tmp_path / "source", version)
    summary = router.inspect_source(source)
    assert summary.renpy_legacy_arm64_candidate is eligible
    manager = RuntimeManager(tmp_path / "cache")
    manager.ensure_full_sdk = lambda *a, **kw: pytest.fail("dry run download")
    if eligible:
        result = build_game(source, output=tmp_path / "out", legacy_arm64_fallback=True,
                            dry_run=True, runtime_manager=manager)
        assert (result.source_version, result.runtime_version) == (version, "7.5.0")
        assert not result.output_path.exists()
    else:
        with pytest.raises(BuildError):
            build_game(source, output=tmp_path / "out", legacy_arm64_fallback=True,
                       dry_run=True, runtime_manager=manager)


@pytest.mark.parametrize("bad", ["contradictory", "weak", "fake", "python3", "no-python2"])
def test_735_requires_authoritative_consistent_python2_layout(tmp_path, bad):
    source = _legacy_renpy_game(tmp_path / "source", "7.3.5")
    if bad == "contradictory":
        (source / "renpy/__init__.py").write_text("version_tuple = (7, 3, 6, 0)\n")
    elif bad == "weak":
        (source / "renpy/versions.py").unlink()
        (source / "renpy/__init__.py").write_text('version = "7.3.5"\n')
    elif bad == "fake":
        (source / "renpy/__init__.py").unlink()
    elif bad == "python3":
        (source / "lib/py3-linux-x86_64").mkdir()
    else:
        (source / "lib/py2-linux-x86_64").rmdir()
    assert not router.inspect_source(source).renpy_legacy_arm64_candidate
    with pytest.raises(BuildError):
        build_game(source, output=tmp_path / "out", legacy_arm64_fallback=True, dry_run=True)
    assert experimental_arm64_fallback("7.3.5", 7) is None


@pytest.mark.parametrize("choice", [True, False, None])
def test_735_main_gui_consent(tmp_path, monkeypatch, choice):
    app = app_for_inspection(tmp_path)
    _legacy_renpy_game(app.source, "7.3.5")
    app._show_inspection(router.inspect_source(app.source))
    assert "7.5.0 EXPERIMENTAL" in app.runtime_button.values["text"]
    prompts, calls, picks = [], [], []
    monkeypatch.setattr(gui, "messagebox", SimpleNamespace(
        askyesnocancel=lambda *a, **kw: prompts.append(a[1]) or choice))
    def pick():
        picks.append(True)
        app.renpy_runtime = tmp_path / "manual"
    app._pick_renpy_runtime = pick
    monkeypatch.setattr(gui, "build_source", lambda *a, **kw: calls.append(kw))
    synchronous_threads(monkeypatch)
    app._start_convert()
    assert len(prompts) == 1 and "cross-minor" in prompts[0]
    if choice is None:
        assert not calls and not picks
    else:
        assert calls[0]["renpy_legacy_arm64_fallback"] is choice
        assert calls[0]["renpy_ddlc_753_migration"] is False
        assert (calls[0]["renpy_runtime"] is None) is choice
        assert bool(picks) is (not choice)


def test_735_complete_engine_package_and_source_preservation(tmp_path, monkeypatch):
    source = _legacy_renpy_game(tmp_path / "source", "7.3.5")
    (source / "game/options.rpyc").write_bytes(b"synthetic compiled settings")
    (source / "pesterquest.app").mkdir()
    (source / "pesterquest.app/mac.so").write_bytes(b"synthetic Mach-O")
    (source / "old.exe").write_bytes(b"synthetic PE")
    before = {p.relative_to(source): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in source.rglob("*") if p.is_file()}
    sdk = _fake_legacy_sdk(tmp_path / "sdk")
    manager = SimpleNamespace(full_sdk_path=lambda *a: sdk, ensure_full_sdk=lambda *a, **kw: sdk)
    monkeypatch.setattr("renframe.builder.RuntimeManager", lambda: manager)
    monkeypatch.setattr(router, "complete_frame_artwork", lambda *a, **kw: None)
    result = router.build_source(source, output=tmp_path / "out", renpy_legacy_arm64_fallback=True)
    assert {p.relative_to(source): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in source.rglob("*") if p.is_file()} == before
    assert (result.output_path / "game/options.rpyc").read_bytes() == before[next(p for p in before if p.as_posix() == "game/options.rpyc")][0]
    assert (result.output_path / "renpy/versions.py").read_bytes() == (sdk / "renpy/versions.py").read_bytes()
    assert not (result.output_path / "pesterquest.app").exists()
    assert not (result.output_path / "old.exe").exists()
    assert not (result.output_path / "lib/py2-linux-x86_64").exists()
    metadata = json.loads((result.output_path / ".megcfbt/package.json").read_text())
    assert metadata["engine_version"] == "7.3.5"
    assert metadata["runtime_engine_version"] == "7.5.0"
    assert metadata["hardware_verification"] == "pending"
    with zipfile.ZipFile(result.archive_path) as package:
        for name in ("launch.sh", "renpy.sh", "install-to-steam.sh"):
            entry = next(e for e in package.infolist() if e.filename.endswith("/" + name))
            assert (entry.external_attr >> 16) & 0o111


def test_735_native_game_extension_still_blocks(tmp_path):
    source = _legacy_renpy_game(tmp_path / "source", "7.3.5")
    (source / "game/plugin.pyd").write_bytes(b"synthetic PE")
    with pytest.raises(BuildError, match="INCOMPATIBLE_NATIVE_CODE"):
        build_game(source, legacy_arm64_fallback=True, dry_run=True)


def test_735_without_approval_never_migrates(tmp_path):
    source = _legacy_renpy_game(tmp_path / "source", "7.3.5")
    manager = RuntimeManager(tmp_path / "cache")
    manager.ensure_full_sdk = lambda *a, **kw: pytest.fail("unapproved migration")
    with pytest.raises(BuildError, match="predates official Linux AArch64"):
        build_game(source, output=tmp_path / "out", runtime_manager=manager)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("main", [unified_main, renframe_main])
def test_cli_shared_legacy_optin(tmp_path, main):
    source = _legacy_renpy_game(tmp_path / "source", "7.3.5")
    assert main(["build", str(source), "--output", str(tmp_path / "out"),
                 "--experimental-legacy-arm64-fallback", "--dry-run"]) == 0
    assert not (tmp_path / "out").exists()


def archive_manager(tmp_path, monkeypatch, mutate=None):
    archive = tmp_path / "renpy-7.5.0-sdkarm.tar.bz2"
    _full_sdkarm_archive(archive)
    sdk = tmp_path / "full-sdk-fixture/renpy-7.5.0-sdkarm"
    if mutate:
        mutate(sdk)
        with tarfile.open(archive, "w:bz2") as handle:
            handle.add(sdk, arcname=sdk.name)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manager = RuntimeManager(tmp_path / "cache", base_url="https://example.invalid")
    monkeypatch.setattr(manager, "_read_url", lambda *a: f"# sha256\n{digest} {archive.name}\n")
    def download(url, path, **kw):
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, path)
    monkeypatch.setattr(manager, "_download", download)
    return manager


def test_750_verified_cache_tamper_repaired(tmp_path, monkeypatch):
    manager = archive_manager(tmp_path, monkeypatch)
    sdk = manager.ensure_full_sdk("7.5.0", "py2")
    original = (sdk / "renpy/versions.py").read_bytes()
    (sdk / "renpy/versions.py").write_text('version = "7.5.3"\n')
    manager.ensure_full_sdk("7.5.0", "py2")
    assert (sdk / "renpy/versions.py").read_bytes() == original
    (sdk / "lib/python2.7/site.py").write_text("tampered")
    manager.ensure_full_sdk("7.5.0", "py2")
    assert (sdk / "lib/python2.7/site.py").read_text() != "tampered"


@pytest.mark.parametrize("missing", ["renpy.py", "renpy.sh", "LICENSE.txt", "lib/python2.7/site.py"])
def test_750_incomplete_sdk_rejected(tmp_path, monkeypatch, missing):
    manager = archive_manager(tmp_path, monkeypatch, lambda sdk: (sdk / missing).unlink())
    with pytest.raises(RuntimeDownloadError, match="missing|AArch64"):
        manager.ensure_full_sdk("7.5.0", "py2")


def test_750_bad_checksum_refused(tmp_path, monkeypatch):
    manager = archive_manager(tmp_path, monkeypatch)
    monkeypatch.setattr(manager, "_read_url", lambda *a: f"# sha256\n{'0' * 64} renpy-7.5.0-sdkarm.tar.bz2\n")
    with pytest.raises(RuntimeDownloadError, match="SHA256"):
        manager.ensure_full_sdk("7.5.0", "py2")


@pytest.mark.parametrize("wrong", ["engine", "elf"])
def test_750_wrong_engine_or_architecture_rejected(tmp_path, monkeypatch, wrong):
    def mutate(sdk):
        if wrong == "engine":
            (sdk / "renpy/versions.py").write_text('version = "7.5.3"\n')
        else:
            for binary in ("renpy", "python"):
                _write_elf(sdk / "lib/py2-linux-aarch64" / binary, machine=62)
    manager = archive_manager(tmp_path, monkeypatch, mutate)
    with pytest.raises(RuntimeDownloadError, match="7.5.0|AArch64"):
        manager.ensure_full_sdk("7.5.0", "py2")
