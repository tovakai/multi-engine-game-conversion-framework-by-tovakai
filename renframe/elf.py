"""Minimal ELF header parsing for architecture identification."""

from __future__ import annotations

import struct
from pathlib import Path

# ELF e_machine values of interest
_EM_386 = 3
_EM_X86_64 = 62
_EM_ARM = 40
_EM_AARCH64 = 183
_EM_PPC = 20
_EM_PPC64 = 21

_MACHINE_NAMES = {
    _EM_386: "x86",
    _EM_X86_64: "x86_64",
    _EM_ARM: "arm",
    _EM_AARCH64: "aarch64",
    _EM_PPC: "ppc",
    _EM_PPC64: "ppc64",
}


def read_elf_architecture(path: Path | str) -> str | None:
    """
    Return the ELF machine architecture string, or None if not a valid ELF.

    Parses only the ELF identification and e_machine fields. Does not shell out.
    """
    path = Path(path)
    try:
        with path.open("rb") as fh:
            header = fh.read(20)
    except OSError:
        return None

    if len(header) < 20:
        return None
    if header[:4] != b"\x7fELF":
        return None

    ei_class = header[4]  # 1 = 32-bit, 2 = 64-bit
    ei_data = header[5]  # 1 = little, 2 = big
    if ei_class not in (1, 2) or ei_data not in (1, 2):
        return None

    endian = "<" if ei_data == 1 else ">"
    # e_machine is a 16-bit field at offset 18 in both ELF32 and ELF64.
    (e_machine,) = struct.unpack_from(f"{endian}H", header, 18)
    return _MACHINE_NAMES.get(e_machine, f"unknown({e_machine})")


def is_elf_file(path: Path | str) -> bool:
    """Return True if the file starts with an ELF magic number."""
    path = Path(path)
    try:
        with path.open("rb") as fh:
            magic = fh.read(4)
    except OSError:
        return False
    return magic == b"\x7fELF"
