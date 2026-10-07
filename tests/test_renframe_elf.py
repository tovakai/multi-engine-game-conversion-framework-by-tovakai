"""Tests for ELF architecture identification."""

from __future__ import annotations

import struct
from pathlib import Path

from renframe.elf import is_elf_file, read_elf_architecture


def _write_elf(path: Path, *, machine: int, bit64: bool = True, little: bool = True) -> None:
    data = bytearray(64)
    data[0:4] = b"\x7fELF"
    data[4] = 2 if bit64 else 1
    data[5] = 1 if little else 2
    data[6] = 1
    endian = "<" if little else ">"
    struct.pack_into(f"{endian}H", data, 16, 3)  # ET_DYN
    struct.pack_into(f"{endian}H", data, 18, machine)
    path.write_bytes(bytes(data))


def test_read_elf_x86_64(tmp_path: Path) -> None:
    path = tmp_path / "libfoo.so"
    _write_elf(path, machine=62)
    assert read_elf_architecture(path) == "x86_64"
    assert is_elf_file(path)


def test_read_elf_aarch64(tmp_path: Path) -> None:
    path = tmp_path / "libbar.so"
    _write_elf(path, machine=183)
    assert read_elf_architecture(path) == "aarch64"


def test_read_elf_arm32(tmp_path: Path) -> None:
    path = tmp_path / "libarm.so"
    _write_elf(path, machine=40, bit64=False)
    assert read_elf_architecture(path) == "arm"


def test_non_elf_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("not an elf", encoding="utf-8")
    assert read_elf_architecture(path) is None
    assert not is_elf_file(path)


def test_truncated_elf_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "short.so"
    path.write_bytes(b"\x7fELF")
    assert read_elf_architecture(path) is None
