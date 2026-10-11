"""Only synthetic data; no original DDLC content is read or distributed."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from renframe.builder import BuildError, build_game
from renframe.ddlc import original_ddlc_candidate
from renframe.inspect_service import inspect_game
from renframe.runtime import RuntimeManager, RuntimeDownloadError
from megcfbt import gui, router
from megcfbt.cli import main as unified_main
from renframe.cli import main as renframe_main
from test_gui_renpy_fallback import app_for_inspection, synchronous_threads
from test_renpy_runtime import _write_elf


def synthetic_source(root: Path, version="6.99.12") -> Path:
    for directory in ("game", "renpy", "characters", "lib/python2.7", "game/saves"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    major, minor, patch = version.split(".")
    (root / "renpy/__init__.py").write_text(f"version_tuple = ({major}, {minor}, {patch}, 0)\n")
    for name in ("audio", "images", "scripts", "fonts"):
        (root / f"game/{name}.rpa").write_bytes(b"synthetic archive placeholder")
    for name in ("DDLC.exe", "DDLC.py", "firstrun", "notes.txt"):
        (root / name).write_bytes(b"synthetic placeholder")
    (root / "characters/monika.chr").write_bytes(b"synthetic character state")
    (root / "game/script_version.txt").write_text("1.1.1\n")
    (root / "game/saves/persistent").write_bytes(b"synthetic persistent state")
    return root


def synthetic_sdk(root: Path) -> Path:
    (root / "renpy").mkdir(parents=True)
    (root / "renpy/__init__.py").write_text("version_tuple = (7, 5, 3, 0)\n")
    (root / "renpy.py").write_text("# synthetic launcher placeholder\n")
    (root / "LICENSE.txt").write_text("Synthetic fixture, not Ren'Py code\n")
    (root / "lib/python2.7").mkdir(parents=True)
    (root / "lib/python2.7/site.py").write_text("# synthetic stdlib placeholder\n")
    _write_elf(root / "lib/py2-linux-aarch64/renpy")
    (root / "renpy.sh").write_text(
        '#!/bin/sh\n'
        'test "$PWD" = "$1" || exit 90\n'
        'if [ "${2:-}" = delete ]; then\n'
        '  rm -f characters/monika.chr\n'
        '  printf "advanced" > game/saves/persistent\n'
        'fi\n'
        'printf "root=%s state=" "$1"\n'
        'cat game/saves/persistent\n'
        'test ! -f characters/monika.chr && printf " missing-character"\n'
        'exit 0\n', newline="\n",
    )
    (root / "renpy.sh").chmod(0o755)
    return root


class FixtureManager:
    def __init__(self, sdk):
        self.sdk = sdk
        self.downloads = 0

    def full_sdk_path(self, release, tag):
        assert (release, tag) == ("7.5.3", "py2")
        return self.sdk

    def ensure_full_sdk(self, release, tag, **kwargs):
        self.downloads += 1
        return self.full_sdk_path(release, tag)


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_literal_699_stays_generation6_with_python2_layout(tmp_path):
    source = synthetic_source(tmp_path / "source")
    inspection = inspect_game(source)
    assert inspection.generation == 6
    assert inspection.renpy_version == "6.99.12"
    assert original_ddlc_candidate(inspection)
    unified = router.inspect_source(source)
    assert unified.renpy_ddlc_753_candidate
    assert "7.5.3" in unified.runtime_kind
    assert unified.compatibility == "NEEDS_TESTING"


def test_original_steam_layout_without_loose_version_marker(tmp_path):
    source = synthetic_source(tmp_path / "source")
    (source / "game/script_version.txt").unlink()
    assert original_ddlc_candidate(inspect_game(source))
    # All missing characters is also a valid persisted state, not a reason
    # for the converter to restore files from a fresh-game template.
    (source / "characters/monika.chr").unlink()
    sdk = synthetic_sdk(tmp_path / "sdk")
    result = build_game(source, output=tmp_path / "out", ddlc_753_migration=True,
                        runtime_manager=FixtureManager(sdk))
    assert (result.output_path / "characters").is_dir()
    assert not list((result.output_path / "characters").iterdir())


@pytest.mark.parametrize("mutation", ["title-only", "wrong-engine", "missing-archive", "conflicting-engine", "plus", "wrong-case", "wrong-game-version", "unknown-character"])
def test_profile_gate_excludes_ambiguous_sources(tmp_path, mutation):
    source = synthetic_source(tmp_path / "DDLC")
    if mutation == "title-only":
        (source / "DDLC.py").unlink()
    elif mutation == "wrong-engine":
        (source / "renpy/__init__.py").write_text("version_tuple = (6, 99, 11, 0)\n")
    elif mutation == "missing-archive":
        (source / "game/fonts.rpa").unlink()
    elif mutation == "conflicting-engine":
        (source / "renpy/versions.py").write_text('version = "7.5.3"\n')
    elif mutation == "plus":
        (source / "UnityPlayer.dll").write_bytes(b"synthetic")
    elif mutation == "wrong-case":
        (source / "DDLC.py").rename(source / "temp.py")
        (source / "temp.py").rename(source / "ddlc.py")
    elif mutation == "wrong-game-version":
        (source / "game/script_version.txt").write_text("1.1.0\n")
    else:
        (source / "characters/other.chr").write_bytes(b"synthetic")
    assert not original_ddlc_candidate(inspect_game(source))
    with pytest.raises(BuildError, match="requires original"):
        build_game(source, output=tmp_path / "out", ddlc_753_migration=True, dry_run=True)


def test_no_automatic_6x_mapping_without_consent(tmp_path):
    source = synthetic_source(tmp_path / "source")
    with pytest.raises(BuildError, match="supports Ren'Py 7"):
        build_game(source, output=tmp_path / "out", dry_run=True)


def test_arbitrary_6x_inspection_is_honest_and_manual_override_still_works(tmp_path):
    source = synthetic_source(tmp_path / "source", version="6.99.11")
    summary = router.inspect_source(source)
    assert not summary.renpy_ddlc_753_candidate
    assert "manual" in summary.runtime_kind
    sdk = synthetic_sdk(tmp_path / "manual")
    with pytest.raises(BuildError, match="generation mismatch"):
        build_game(source, runtime=sdk, output=tmp_path / "out", dry_run=True)
    result = build_game(source, runtime=sdk, output=tmp_path / "out", dry_run=True,
                        allow_version_mismatch=True)
    assert result.runtime_version == "7.5.3"


def test_ddlc_manual_migration_preserves_characters_with_explicit_mismatch(tmp_path):
    source = synthetic_source(tmp_path / "source")
    sdk = synthetic_sdk(tmp_path / "manual")
    result = build_game(source, runtime=sdk, output=tmp_path / "out",
                        allow_version_mismatch=True)
    assert (result.output_path / "characters/monika.chr").read_bytes() == b"synthetic character state"


def test_unified_optin_rejects_wrong_engine_before_build(tmp_path):
    source = tmp_path / "plus"
    source.mkdir()
    (source / "DDLC Plus.exe").write_bytes(b"synthetic executable")
    (source / "UnityPlayer.dll").write_bytes(b"synthetic Unity marker")
    with pytest.raises(router.ConversionError, match="requires original DDLC"):
        router.build_source(source, renpy_ddlc_753_migration=True, dry_run=True)


def test_ddlc_dry_run_has_no_download_or_output(tmp_path):
    source = synthetic_source(tmp_path / "source")
    manager = FixtureManager(tmp_path / "sdk-does-not-exist")
    result = build_game(source, output=tmp_path / "out", ddlc_753_migration=True,
                        dry_run=True, runtime_manager=manager)
    assert result.source_version == "6.99.12"
    assert result.runtime_version == "7.5.3"
    assert result.runtime_architecture == "aarch64"
    assert manager.downloads == 0
    assert not result.output_path.exists()


@pytest.mark.parametrize("entry", ["unified", "renframe"])
def test_cli_optin_dry_run(tmp_path, entry):
    source = synthetic_source(tmp_path / "source")
    main = unified_main if entry == "unified" else renframe_main
    assert main(["build", str(source), "--output", str(tmp_path / "out"),
                 "--experimental-ddlc-753-migration", "--dry-run"]) == 0
    assert not (tmp_path / "out").exists()


def test_migration_preserves_payload_sidecars_missing_state_and_source(tmp_path):
    source = synthetic_source(tmp_path / "source")
    sdk = synthetic_sdk(tmp_path / "sdk")
    original = snapshot(source)
    result = build_game(source, output=tmp_path / "out", ddlc_753_migration=True,
                        runtime_manager=FixtureManager(sdk))
    out = result.output_path
    assert snapshot(source) == original
    for relative, data in original.items():
        if relative.startswith(("game/", "characters/")) or relative in {"notes.txt", "firstrun"}:
            assert (out / relative).read_bytes() == data
    assert not (out / "characters/sayori.chr").exists()
    assert not (out / "DDLC.exe").exists()
    assert not (out / "DDLC.py").exists()
    assert (out / "renpy/__init__.py").read_bytes() == (sdk / "renpy/__init__.py").read_bytes()
    bash = shutil.which("bash")
    if bash:
        # Use a POSIX path under Git Bash on Windows.
        launcher = result.launcher_path.as_posix()
        if launcher[1:3] == ":/":
            launcher = "/" + launcher[0].lower() + launcher[2:]
        for argument in ("delete", "restart"):
            run = subprocess.run([bash, launcher, argument], cwd=tmp_path,
                                 check=True, capture_output=True, text=True)
            assert "advanced" in run.stdout and "missing-character" in run.stdout
        assert snapshot(source) == original
        assert not (out / "characters/monika.chr").exists()
        assert (out / "game/saves/persistent").read_bytes() == b"advanced"


@pytest.mark.parametrize("choice", [True, False, None])
def test_gui_ddlc_yes_no_cancel(tmp_path, monkeypatch, choice):
    app = app_for_inspection(tmp_path)
    synthetic_source(app.source)
    app.inspection = router.inspect_source(app.source)
    app._show_inspection(app.inspection)
    assert "7.5.3 EXPERIMENTAL" in app.runtime_button.values["text"]
    prompts, calls = [], []
    monkeypatch.setattr(gui, "messagebox", SimpleNamespace(
        askyesnocancel=lambda *a, **kw: prompts.append(a[1]) or choice,
    ))
    app._pick_renpy_runtime = lambda: setattr(app, "renpy_runtime", tmp_path / "manual")
    monkeypatch.setattr(gui, "build_source", lambda *a, **kw: calls.append(kw))
    synchronous_threads(monkeypatch)
    app._start_convert()
    assert len(prompts) == 1 and "NOT hardware verified" in prompts[0]
    if choice is None:
        assert not calls
    else:
        assert calls[0]["renpy_ddlc_753_migration"] is choice
        assert calls[0]["renpy_legacy_arm64_fallback"] is False
        assert (calls[0]["renpy_runtime"] is None) is choice


def test_gui_ddlc_manual_override_never_prompts(tmp_path, monkeypatch):
    app = app_for_inspection(tmp_path)
    synthetic_source(app.source)
    app.inspection = router.inspect_source(app.source)
    app.renpy_runtime = tmp_path / "manual"
    monkeypatch.setattr(gui, "messagebox", SimpleNamespace(
        askyesnocancel=lambda *a, **kw: pytest.fail("unexpected prompt"),
    ))
    calls = []
    monkeypatch.setattr(gui, "build_source", lambda *a, **kw: calls.append(kw))
    synchronous_threads(monkeypatch)
    app._start_convert()
    assert calls[0]["renpy_ddlc_753_migration"] is False


def test_unified_zip_metadata_and_no_artwork_network(tmp_path, monkeypatch):
    source = synthetic_source(tmp_path / "source")
    sdk = synthetic_sdk(tmp_path / "sdk")
    monkeypatch.setattr("renframe.builder.RuntimeManager", lambda: FixtureManager(sdk))
    monkeypatch.setattr(router, "complete_frame_artwork", lambda *a, **kw: pytest.fail("artwork network"))
    result = router.build_source(source, output=tmp_path / "out", renpy_ddlc_753_migration=True)
    metadata = json.loads((result.output_path / ".megcfbt/package.json").read_text())
    assert metadata["engine_version"] == "6.99.12"
    assert metadata["runtime_engine_version"] == "7.5.3"
    assert metadata["hardware_verification"] == "pending"
    with zipfile.ZipFile(result.archive_path) as package:
        assert any(n.endswith("characters/monika.chr") for n in package.namelist())
        assert any(n.endswith("install-to-steam.sh") for n in package.namelist())
        entry = next(e for e in package.infolist() if e.filename.endswith("renpy.sh"))
        assert (entry.external_attr >> 16) & 0o111


def mock_archive_manager(tmp_path, monkeypatch, *, extra=None, mutate_sdk=None):
    sdk = synthetic_sdk(tmp_path / "archive-src/renpy-7.5.3-sdkarm")
    if mutate_sdk:
        mutate_sdk(sdk)
    archive = tmp_path / "renpy-7.5.3-sdkarm.tar.bz2"
    with tarfile.open(archive, "w:bz2") as handle:
        handle.add(sdk, arcname=sdk.name)
        if extra:
            extra(handle)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manager = RuntimeManager(tmp_path / "cache", base_url="https://example.invalid/dl")
    monkeypatch.setattr(manager, "_read_url", lambda url: f"# sha256\n{digest} {archive.name}\n")
    calls = []
    def download(url, path, **kwargs):
        calls.append(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, path)
    monkeypatch.setattr(manager, "_download", download)
    return manager, calls


def test_753_sha_cache_and_tamper_repair(tmp_path, monkeypatch):
    manager, calls = mock_archive_manager(tmp_path, monkeypatch)
    path = manager.ensure_full_sdk("7.5.3", "py2")
    assert manager.ensure_full_sdk("7.5.3", "py2") == path
    assert len(calls) == 1
    (path / "renpy/__init__.py").write_text("tampered")
    assert manager.ensure_full_sdk("7.5.3", "py2") == path
    assert "version_tuple" in (path / "renpy/__init__.py").read_text()
    assert len(calls) == 1  # verified download reused, extracted tree repaired


def test_753_bad_sha_refused_before_extraction(tmp_path, monkeypatch):
    manager, calls = mock_archive_manager(tmp_path, monkeypatch)
    monkeypatch.setattr(manager, "_read_url", lambda url: f"# sha256\n{'0' * 64} renpy-7.5.3-sdkarm.tar.bz2\n")
    with pytest.raises(RuntimeDownloadError, match="SHA256"):
        manager.ensure_full_sdk("7.5.3", "py2")
    assert not manager.full_sdk_path("7.5.3", "py2").exists()


@pytest.mark.parametrize("missing", ["renpy.py", "renpy.sh", "LICENSE.txt", "lib/python2.7/site.py", "lib/py2-linux-aarch64/renpy"])
def test_753_incomplete_layout_rejected(tmp_path, monkeypatch, missing):
    manager, calls = mock_archive_manager(tmp_path, monkeypatch,
                                         mutate_sdk=lambda sdk: (sdk / missing).unlink())
    with pytest.raises(RuntimeDownloadError, match="missing|AArch64"):
        manager.ensure_full_sdk("7.5.3", "py2")
    assert not manager.full_sdk_path("7.5.3", "py2").exists()


@pytest.mark.parametrize("wrong", ["engine", "elf"])
def test_753_wrong_engine_or_architecture_rejected(tmp_path, monkeypatch, wrong):
    def mutate(sdk):
        if wrong == "engine":
            (sdk / "renpy/__init__.py").write_text("version_tuple = (8, 0, 3, 0)\n")
        else:
            _write_elf(sdk / "lib/py2-linux-aarch64/renpy", machine=62)
    manager, calls = mock_archive_manager(tmp_path, monkeypatch, mutate_sdk=mutate)
    with pytest.raises(RuntimeDownloadError, match="7.5.3|AArch64"):
        manager.ensure_full_sdk("7.5.3", "py2")


def test_753_malformed_cache_manifest_is_repaired(tmp_path, monkeypatch):
    manager, calls = mock_archive_manager(tmp_path, monkeypatch)
    path = manager.ensure_full_sdk("7.5.3", "py2")
    (path / ".verified-sdk.json").write_text("[]")
    manager.ensure_full_sdk("7.5.3", "py2")
    assert isinstance(json.loads((path / ".verified-sdk.json").read_text()), dict)
    assert len(calls) == 1


@pytest.mark.parametrize("bad_name", ["../outside", "/absolute", "C:/outside", "renpy-7.5.3-sdkarm/renpy\\evil", "renpy-7.5.3-sdkarm/renpy/__init__.py"])
def test_753_bad_archive_paths(tmp_path, monkeypatch, bad_name):
    def add_bad(handle):
        entry = tarfile.TarInfo(bad_name)
        entry.size = 1
        handle.addfile(entry, io.BytesIO(b"x"))
    manager, calls = mock_archive_manager(tmp_path, monkeypatch, extra=add_bad)
    with pytest.raises(RuntimeDownloadError, match="unsafe|colliding"):
        manager.ensure_full_sdk("7.5.3", "py2")
    assert not manager.full_sdk_path("7.5.3", "py2").exists()


@pytest.mark.parametrize("link", ["../../outside", "/outside", "C:/outside"])
def test_753_bad_links(tmp_path, monkeypatch, link):
    def add_bad(handle):
        entry = tarfile.TarInfo("renpy-7.5.3-sdkarm/renpy/unsafe")
        entry.type = tarfile.SYMTYPE
        entry.linkname = link
        handle.addfile(entry)
    manager, calls = mock_archive_manager(tmp_path, monkeypatch, extra=add_bad)
    with pytest.raises(RuntimeDownloadError, match="unsafe link"):
        manager.ensure_full_sdk("7.5.3", "py2")


def test_753_special_file_refused(tmp_path, monkeypatch):
    def add_bad(handle):
        entry = tarfile.TarInfo("renpy-7.5.3-sdkarm/renpy/device")
        entry.type = tarfile.CHRTYPE
        handle.addfile(entry)
    manager, calls = mock_archive_manager(tmp_path, monkeypatch, extra=add_bad)
    with pytest.raises(RuntimeDownloadError, match="special file"):
        manager.ensure_full_sdk("7.5.3", "py2")


def test_no_download_for_unsafe_existing_output(tmp_path):
    source = synthetic_source(tmp_path / "source")
    manager = FixtureManager(tmp_path / "sdk")
    for output in (source / "nested", tmp_path / "existing"):
        if output.name == "existing":
            output.mkdir()
        with pytest.raises(BuildError, match="conflicts|already exists"):
            build_game(source, output=output, ddlc_753_migration=True, runtime_manager=manager)
    assert manager.downloads == 0


def test_partial_copy_failure_preserves_source_and_existing_output(tmp_path, monkeypatch):
    source = synthetic_source(tmp_path / "source")
    sdk = synthetic_sdk(tmp_path / "sdk")
    output = tmp_path / "out"
    output.mkdir()
    (output / "keep.txt").write_text("existing output")
    original = snapshot(source)
    real_copy = shutil.copy2
    def broken_copy(src, dst, **kwargs):
        if Path(src).name == "firstrun":
            raise OSError("synthetic failed copy")
        return real_copy(src, dst, **kwargs)
    monkeypatch.setattr(shutil, "copy2", broken_copy)
    with pytest.raises(BuildError, match="failed copy"):
        build_game(source, output=output, ddlc_753_migration=True, force=True,
                   runtime_manager=FixtureManager(sdk))
    assert snapshot(source) == original
    assert snapshot(output) == {"keep.txt": b"existing output"}
    assert not list(tmp_path.glob(".out.tmp-*"))


def test_migration_conflicting_options_and_overlap_refused(tmp_path):
    source = synthetic_source(tmp_path / "source")
    for options in ({"runtime": tmp_path / "manual"}, {"legacy_arm64_fallback": True}):
        with pytest.raises(BuildError, match="Choose DDLC"):
            build_game(source, ddlc_753_migration=True, dry_run=True, **options)
    with pytest.raises(BuildError, match="conflicts with source"):
        build_game(source, output=source / "out", ddlc_753_migration=True,
                   dry_run=True, runtime_manager=FixtureManager(tmp_path / "sdk"))
