"""Minimal ELF architecture inspection."""

from __future__ import annotations

from pathlib import Path

_MACHINE_NAMES = {
    3: "x86",
    40: "arm",
    62: "x86_64",
    183: "aarch64",
}


def read_elf_architecture(path: Path) -> str | None:
    """Return a simple architecture label for an ELF binary."""
    try:
        header = path.read_bytes()[:20]
    except OSError:
        return None

    if len(header) < 20 or header[:4] != b"\x7fELF":
        return None

    byte_order = header[5]
    if byte_order == 1:
        machine = int.from_bytes(header[18:20], "little")
    elif byte_order == 2:
        machine = int.from_bytes(header[18:20], "big")
    else:
        return None

    return _MACHINE_NAMES.get(machine, f"elf-machine-{machine}")
