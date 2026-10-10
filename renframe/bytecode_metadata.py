"""Bounded, non-executing metadata reader for released CPython bytecode formats."""
from pathlib import Path
import struct

# Magic -> (pyc header size, code header integers, wordcode, literal opcodes).
# Read only co_code/co_consts/co_names; never construct or execute a code object.
_FORMATS = {
    62211: (8, 4, False, 100, {90, 97}),
    3230: (12, 5, False, 100, {90, 97}),
    3310: (12, 5, False, 100, {90, 97}),
    3350: (12, 5, False, 100, {90, 97}),
    3351: (12, 5, False, 100, {90, 97}),
    3379: (12, 5, True, 100, {90, 97}),
    3394: (16, 5, True, 100, {90, 97}),
    3413: (16, 6, True, 100, {90, 97}),
    3425: (16, 6, True, 100, {90, 97}),
    3439: (16, 6, True, 100, {90, 97}),
    3495: (16, 5, True, 100, {90, 97}),
    3531: (16, 5, True, 100, {90, 97}),
    3571: (16, 5, True, 83, {113, 114}),
}
_PENDING = object()


class _Reader:
    def __init__(self, data):
        self.data, self.pos, self.refs, self.interned = data, 0, [], []

    def read(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError("truncated metadata")
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def integer(self):
        return struct.unpack("<i", self.read(4))[0]

    def value(self, depth=0):
        if depth > 16 or len(self.refs) > 4096:
            raise ValueError("metadata complexity limit")
        raw = self.read(1)[0]
        tag = chr(raw & 127)
        slot = None
        if raw & 128:
            slot = len(self.refs)
            self.refs.append(_PENDING)
        if tag in {"N", "F", "T"}:
            value = {"N": None, "F": False, "T": True}[tag]
        elif tag == "i":
            value = self.integer()
        elif tag in {"s", "t", "u", "a", "A", "z", "Z"}:
            size = self.read(1)[0] if tag in {"z", "Z"} else self.integer()
            value = self.read(size)
            if tag in {"u", "a", "A", "z", "Z"}:
                value = value.decode("utf-8")
            if tag == "t":
                self.interned.append(value)
        elif tag in {"(", ")"}:
            size = self.read(1)[0] if tag == ")" else self.integer()
            if not 0 <= size <= 4096:
                raise ValueError("metadata tuple limit")
            value = tuple(self.value(depth + 1) for _ in range(size))
        elif tag in {"r", "R"}:
            index = self.integer()
            pool = self.refs if tag == "r" else self.interned
            if not 0 <= index < len(pool) or pool[index] is _PENDING:
                raise ValueError("invalid metadata reference")
            value = pool[index]
        else:
            raise ValueError("unsupported metadata object")
        if slot is not None:
            self.refs[slot] = value
        return value


def literal_assignments(path: Path) -> dict:
    """Read literal module assignments in a small pyc, independent of host Python."""
    try:
        with path.open("rb") as stream:
            data = stream.read(65537)
        if len(data) > 65536 or len(data) < 8 or data[2:4] != b"\r\n":
            return {}
        fmt = _FORMATS.get(int.from_bytes(data[:2], "little"))
        if fmt is None:
            return {}
        header, integers, wordcode, load, stores = fmt
        reader = _Reader(data[header:])
        tag = reader.read(1)[0]
        if tag & 127 != ord("c"):
            return {}
        if tag & 128:
            reader.refs.append(_PENDING)
        reader.read(integers * 4)
        code, constants, names = reader.value(), reader.value(), reader.value()
        if not isinstance(code, bytes) or not isinstance(constants, tuple) or not isinstance(names, tuple):
            return {}
        instructions = []
        pos = 0
        while pos < len(code):
            opcode = code[pos]
            pos += 1
            arg = None
            if wordcode:
                arg = code[pos]
                pos += 1
            elif opcode >= 90:
                if pos + 2 > len(code):
                    return {}
                arg = int.from_bytes(code[pos:pos + 2], "little")
                pos += 2
            instructions.append((opcode, arg))
        found, conflicts = {}, set()
        for (previous, const), (opcode, name) in zip(instructions, instructions[1:]):
            if previous != load or opcode not in stores:
                continue
            if const is None or name is None or const >= len(constants) or name >= len(names):
                continue
            key = names[name]
            if isinstance(key, bytes):
                key = key.decode("ascii")
            if key not in {"version", "vc_version", "nightly", "official", "branch", "version_name"}:
                continue
            value = constants[const]
            if isinstance(value, bytes):
                value = value.decode("ascii")
            if key in found and found[key] != value:
                conflicts.add(key)
            found[key] = value
        return {key: value for key, value in found.items() if key not in conflicts}
    except (OSError, ValueError, UnicodeError, IndexError, struct.error):
        return {}
