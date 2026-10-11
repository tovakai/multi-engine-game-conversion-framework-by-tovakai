"""Bounded, hash-verified input access and non-overwriting publication."""

from contextlib import contextmanager
import ctypes
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import sys

from inventory_package import identity, COMPARE_HANDLE_PATH_STATS


BLOCK = 1024 * 1024


def safe(path):
    path = Path(os.path.abspath(Path(path).expanduser()))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symbolic link refused: " + str(path))
    return path


def relative(value):
    p = PurePosixPath(value)
    if (not value or "\\" in value or ":" in value or p.is_absolute()
            or p.as_posix() != value or ".." in p.parts):
        raise ValueError("Unsafe relative path")
    return Path(*p.parts)


@contextmanager
def verified_stream(path, pin):
    path = safe(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != pin["size_bytes"]:
        raise ValueError("Missing or wrong-sized input: " + str(path))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("Input is not a regular file")
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(BLOCK), b""):
            digest.update(block)
        if digest.hexdigest() != pin["sha256"]:
            raise ValueError("Unsupported or altered input SHA-256: " + str(path))
        stream.seek(0)
        yield stream
        if (identity(before) != identity(path.lstat())
                or identity(opened) != identity(os.fstat(stream.fileno()))
                or (COMPARE_HANDLE_PATH_STATS and identity(before) != identity(opened))):
            raise ValueError("Input changed while being used: " + str(path))


def read_verified(path, pin, limit=64 * BLOCK):
    if pin["size_bytes"] > limit:
        raise ValueError("Input exceeds memory limit")
    with verified_stream(path, pin) as stream:
        raw = stream.read(limit + 1)
    if len(raw) != pin["size_bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("Input changed while reading")
    return raw


def write_new(path, raw, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(mode)


def publish_new(source, destination):
    """Atomic no-replace rename on supported converter hosts, including directories."""
    source, destination = safe(source), safe(destination)
    if os.name == "nt":
        os.rename(source, destination)  # Windows rename refuses existing targets.
    elif sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        if not hasattr(libc, "renameat2"):
            raise OSError("Host lacks renameat2; refusing an overwriting publication fallback")
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(destination))
    else:
        raise OSError("Converter publication currently supports Windows and Linux hosts only")
