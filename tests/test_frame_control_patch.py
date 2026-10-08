from __future__ import annotations

from pathlib import Path

import pytest

from megcfbt import frame_control_patch as patch


STOCK = b"""from pathlib import Path
MAX_UPLOAD = 8 * 1024**3
MAX_JSON = 1024**2
"""

PATCHED = STOCK.replace(b"MAX_UPLOAD = 8 * 1024**3", b"MAX_UPLOAD = 20 * 1024**3")


def make_server(tmp_path: Path, data: bytes = STOCK) -> Path:
    server = tmp_path / "Frame Control" / "resources" / "ui" / "server.py"
    server.parent.mkdir(parents=True)
    server.write_bytes(data)
    return server


def test_patch_and_restore_are_exact_and_reversible(tmp_path):
    server = make_server(tmp_path)

    before = patch.inspect_frame_control(server)
    assert before.is_stock
    assert before.limit_gib == 8
    assert not before.has_backup

    after = patch.patch_upload_limit(server)
    assert after.is_patched
    assert after.limit_gib == 20
    assert after.has_backup
    assert server.read_bytes() == PATCHED
    assert after.backup_path.read_bytes() == STOCK

    restored = patch.restore_upload_limit(server)
    assert restored.is_stock
    assert restored.limit_gib == 8
    assert server.read_bytes() == STOCK
    assert not restored.backup_path.exists()


def test_patching_twice_keeps_original_backup(tmp_path):
    server = make_server(tmp_path)
    first = patch.patch_upload_limit(server)
    original_backup = first.backup_path.read_bytes()

    second = patch.patch_upload_limit(server)

    assert second.is_patched
    assert second.backup_path.read_bytes() == original_backup == STOCK


def test_custom_limit_is_reported_but_not_overwritten(tmp_path):
    server = make_server(
        tmp_path,
        STOCK.replace(b"MAX_UPLOAD = 8 * 1024**3", b"MAX_UPLOAD = 12 * 1024**3"),
    )

    status = patch.inspect_frame_control(server)
    assert status.limit_gib == 12
    assert not status.is_stock
    assert not status.is_patched

    with pytest.raises(patch.FrameControlPatchError, match="custom 12 GiB"):
        patch.patch_upload_limit(server)


def test_unknown_upstream_layout_is_refused(tmp_path):
    server = make_server(
        tmp_path,
        STOCK.replace(b"MAX_UPLOAD = 8 * 1024**3", b"MAX_UPLOAD = 8 << 30"),
    )

    with pytest.raises(patch.FrameControlPatchError, match="does not contain the expected"):
        patch.inspect_frame_control(server)


def test_locates_packaged_windows_server_from_exe(tmp_path):
    server = make_server(tmp_path)
    exe = tmp_path / "Frame Control" / "Frame Control.exe"
    exe.write_bytes(b"MZ")

    assert patch.locate_frame_control_server(exe) == server.resolve()


def test_auto_locates_common_localappdata_install(tmp_path, monkeypatch):
    local = tmp_path / "Local"
    server = local / "Programs" / "Frame Control" / "resources" / "ui" / "server.py"
    server.parent.mkdir(parents=True)
    server.write_bytes(STOCK)

    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("FRAME_CONTROL_SERVER", raising=False)
    monkeypatch.chdir(tmp_path)

    assert patch.locate_frame_control_server() == server.resolve()


def test_restore_refuses_missing_backup_for_custom_file(tmp_path):
    server = make_server(tmp_path, PATCHED)

    with pytest.raises(patch.FrameControlPatchError, match="No backup exists"):
        patch.restore_upload_limit(server)
