"""Extract only explicitly selected regular files from a Unity xar/gzip/odc package.

Format approach informed by DaVarga/bs-arm64's MIT-licensed unity_pkg_extract.py
at 5a318356703ac3835ee62bba677ba0778c76c7c5. See licenses/bs-arm64-MIT.txt.
No package paths are used as destination paths: callers supply an exact map.
"""
from __future__ import annotations

import gzip
import shutil
import struct
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path


CHUNK = 1024 * 1024


def read_exact(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise ValueError('Truncated package')
    return data


class LimitedReader:
    def __init__(self, stream, length):
        self.stream = stream
        self.remaining = length

    def read(self, count=-1):
        count = self.remaining if count < 0 else min(count, self.remaining)
        data = self.stream.read(count)
        self.remaining -= len(data)
        return data


def extract_selected(package: Path, destinations: dict[str, Path]):
    """Extract an exact allowlist; reject duplicate, nonregular and oversized targets."""
    found = set()
    with package.open('rb') as source:
        magic, header_size, version, toc_length, raw_length, _ = struct.unpack(
            '>4sHHQQI', read_exact(source, 28))
        if magic != b'xar!' or version != 1 or not 28 <= header_size <= 4096:
            raise ValueError('Unsupported xar header')
        if toc_length > 16 * CHUNK or raw_length > 64 * CHUNK:
            raise ValueError('Oversized xar table of contents')
        source.seek(header_size)
        inflater = zlib.decompressobj()
        toc = inflater.decompress(read_exact(source, toc_length), raw_length + 1)
        if len(toc) != raw_length or not inflater.eof or inflater.unused_data:
            raise ValueError('Invalid xar table of contents')
        root = ET.fromstring(toc)
        payloads = [entry.find('data') for entry in root.iter('file')
                    if entry.findtext('name') in {'Payload', 'Payload~'}]
        if len(payloads) != 1 or payloads[0] is None:
            raise ValueError('Expected one package payload')
        offset = int(payloads[0].findtext('offset'))
        length = int(payloads[0].findtext('length'))
        start = header_size + toc_length + offset
        if offset < 0 or length <= 0 or start + length > package.stat().st_size:
            raise ValueError('Invalid payload bounds')
        source.seek(start)
        with gzip.GzipFile(fileobj=LimitedReader(source, length)) as payload:
            for _ in range(100000):
                header = read_exact(payload, 76)
                if header[:6] != b'070707':
                    raise ValueError('Unsupported cpio format')
                mode = int(header[18:24], 8)
                name_size = int(header[59:65], 8)
                size = int(header[65:76], 8)
                if not 1 <= name_size <= 4096:
                    raise ValueError('Invalid member name size')
                raw_name = read_exact(payload, name_size)
                if raw_name[-1:] != b'\0':
                    raise ValueError('Member name is not terminated')
                name = raw_name[:-1].decode('utf-8', 'strict')
                if name.startswith('./'):
                    name = name[2:]
                if name == 'TRAILER!!!':
                    # Consume the gzip trailer to validate CRC even after cpio ends.
                    shutil.copyfileobj(payload, _Discard(), CHUNK)
                    break
                destination = destinations.get(name)
                if destination is not None:
                    if name in found or mode & 0o170000 != 0o100000 or size > 256 * CHUNK:
                        raise ValueError(f'Invalid selected member: {name}')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('xb') as output:
                        _copy_size(payload, output, size)
                    found.add(name)
                else:
                    _copy_size(payload, _Discard(), size)
            else:
                raise ValueError('Too many cpio members')
    missing = destinations.keys() - found
    if missing:
        raise ValueError(f'Missing player files: {sorted(missing)}')


class _Discard:
    def write(self, data):
        return len(data)


def _copy_size(source, destination, size):
    while size:
        chunk = read_exact(source, min(size, CHUNK))
        destination.write(chunk)
        size -= len(chunk)
