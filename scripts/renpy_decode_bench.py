"""Python 2/3 benchmark using the installed runtime's pygame_sdl2 decoder.

Usage: payload/lib/py2-linux-aarch64/python -O renpy_decode_bench.py payload
No game initialization, display, script execution, save writes, or asset changes.
Index globals are rejected. Reports repeated reads/decodes, NOT scene timings.
"""
from __future__ import print_function
import io
import ctypes
import json
import os
import pickle
import struct
import sys
import time
import zlib


class RestrictedIndex(pickle.Unpickler):
    def find_class(self, module, name):
        raise ValueError("Executable pickle global rejected")

    def find_global(self, module, name):
        raise ValueError("Executable pickle global rejected")


def run(root):
    sys.path.insert(0, os.path.join(root, "lib", "py2-linux-aarch64"))
    sys.path.insert(0, os.path.join(root, "lib", "python2.7"))
    import pygame_sdl2.image
    clock = getattr(time, "perf_counter", time.time)
    archive = os.path.join(root, "game", "archive.rpa")
    with open(archive, "rb") as stream:
        header = stream.read(40)
        if not header.startswith(b"RPA-3.0 "):
            raise ValueError("Requires RPA-3")
        key = int(header[25:33], 16)
        stream.seek(int(header[8:24], 16))
        index = RestrictedIndex(io.BytesIO(zlib.decompress(stream.read()))).load()
        candidates = []
        for name, chunks in index.items():
            if not name.endswith(".png") or len(chunks) != 1:
                continue
            chunk = chunks[0]
            candidates.append((chunk[1] ^ key, name, chunk))
        # Select by encoded size from the index, avoiding thousands of random reads.
        candidates.sort(reverse=True)
        selected = [candidates[0], candidates[len(candidates)//2], candidates[-1]]
        results = []
        def physical_bytes():
            with open("/proc/self/io") as info:
                return int([line.split()[1] for line in info if line.startswith("read_bytes:")][0])
        for encoded_size, name, chunk in selected:
            offset, length = chunk[0] ^ key, chunk[1] ^ key
            prefix = chunk[2] if len(chunk) == 3 else b""
            for iteration in range(5):
                evict_result = None
                if iteration == 0 and "--advise-cold" in sys.argv:
                    # Advisory eviction of this asset's file range only. Never
                    # writes drop_caches or alters global/device configuration.
                    libc = ctypes.CDLL(None)
                    advise = libc.posix_fadvise
                    advise.argtypes = [ctypes.c_int, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_int]
                    evict_result = advise(stream.fileno(), offset // 4096 * 4096,
                                          ((offset % 4096 + length + 4095) // 4096) * 4096, 4)
                physical_before = physical_bytes()
                started = clock()
                stream.seek(offset)
                data = prefix + stream.read(length)
                read_ms = (clock()-started)*1000
                width, height = struct.unpack(">II", data[16:24])
                started = clock()
                surface = pygame_sdl2.image.load(io.BytesIO(data), name)
                decode_ms = (clock()-started)*1000
                del surface
                results.append(dict(asset=name, width=width, height=height,
                                    bytes=len(data), iteration=iteration,
                                    advised_cold=evict_result == 0,
                                    physical_read_bytes=physical_bytes()-physical_before,
                                    read_ms=read_ms, decode_ms=decode_ms))
        print(json.dumps(dict(root=root, python=sys.version, results=results), indent=2))


if __name__ == "__main__":
    run(os.path.abspath(sys.argv[1]))
