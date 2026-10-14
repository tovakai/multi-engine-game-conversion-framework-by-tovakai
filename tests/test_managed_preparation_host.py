from pathlib import Path
import pytest
from monoframe import preparation
from test_native_backends import elf


def test_windows_uses_existing_windows_preparer(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation.sys, 'platform', 'win32')
    assert preparation.preparation_command(tmp_path, 'CelestePrepare') == [str(tmp_path / 'prepare/windows-x64/CelestePrepare.exe')]


def test_arm_linux_uses_packaged_arm_dotnet(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation.sys, 'platform', 'linux')
    monkeypatch.setattr(preparation.platform, 'machine', lambda: 'aarch64')
    assert preparation.preparation_command(tmp_path, 'CelestePrepare')[0] == str(tmp_path / 'dotnet/dotnet')


def test_x64_linux_uses_native_host_not_arm_game_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation.sys, 'platform', 'linux')
    monkeypatch.setattr(preparation.platform, 'machine', lambda: 'x86_64')
    host = tmp_path / 'dotnet'
    elf(host, 62)
    monkeypatch.setattr(preparation.shutil, 'which', lambda name: str(host))
    command = preparation.preparation_command(tmp_path / 'sdk', 'CelestePrepare')
    assert command == [str(host), str(tmp_path / 'sdk/prepare/managed/CelestePrepare.dll')]
    elf(host, 183)
    with pytest.raises(RuntimeError, match='native x64'):
        preparation.preparation_command(tmp_path / 'sdk', 'CelestePrepare')
    monkeypatch.setattr(preparation.shutil, 'which', lambda name: None)
    with pytest.raises(RuntimeError, match='native x64'):
        preparation.preparation_command(tmp_path / 'sdk', 'MainlineGameDataPatcher')
