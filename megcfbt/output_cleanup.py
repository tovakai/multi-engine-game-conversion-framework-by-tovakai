"""Remove GUI work copies only after verifying their portable ZIP."""
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import stat
import zipfile
import zlib


def finish_gui_conversion(result, progress=None):
    if not result.archive_path or result.requires_frame_install or result.remote_job:
        return result
    output = Path(result.output_path).absolute()
    archive = Path(result.archive_path).absolute()
    source = Path(result.source_path).resolve()
    try:
        if output.is_symlink() or output.is_junction() or archive.is_symlink():
            raise ValueError('work directory or ZIP is a link')
        root = output.resolve()
        if root == source or root in source.parents or source in root.parents:
            raise ValueError('work directory overlaps the original source')
        if archive.resolve() == root or root in archive.resolve().parents:
            raise ValueError('ZIP is inside the work directory')
        if progress:
            progress('Verifying ZIP before removing the temporary conversion directory')
        metadata = json.loads((root / '.megcfbt/package.json').read_text(encoding='utf-8'))
        prefix = root.name + '/payload/'
        with zipfile.ZipFile(archive) as packaged:
            if len(packaged.namelist()) != len(set(packaged.namelist())):
                raise ValueError('ZIP contains duplicate paths')
            if packaged.testzip() is not None:
                raise ValueError('ZIP integrity check failed')
            zipped = json.loads(packaged.read(prefix + '.megcfbt/package.json'))
            if {key: value for key, value in zipped.items() if key != 'packaging'} != {
                    key: value for key, value in metadata.items() if key != 'packaging'}:
                raise ValueError('ZIP metadata differs from the work copy')
            # Preserve anything added/changed after packaging, including saves.
            for directory, dirs, files in os.walk(root, followlinks=False):
                for name in dirs + files:
                    path = Path(directory) / name
                    if path.is_junction():
                        raise ValueError('work copy contains a filesystem junction')
                    relative = path.relative_to(root).as_posix()
                    if relative == '.megcfbt/package.json':
                        continue
                    if path.is_symlink():
                        data = os.readlink(path).encode('utf-8')
                        info = packaged.getinfo(prefix + relative)
                        if stat.S_IFMT(info.external_attr >> 16) != stat.S_IFLNK or packaged.read(info) != data:
                            raise ValueError(f'link changed after packaging: {relative}')
                    elif path.is_dir():
                        packaged.getinfo(prefix + relative + '/')
                    elif path.is_file():
                        info = packaged.getinfo(prefix + relative)
                        before = path.stat()
                        crc = 0
                        with path.open('rb') as stream:
                            while chunk := stream.read(1 << 20):
                                crc = zlib.crc32(chunk, crc)
                        if path.stat() != before or before.st_size != info.file_size or crc != info.CRC:
                            raise ValueError(f'file changed after packaging: {relative}')
                    else:
                        raise ValueError(f'unsupported work-copy file: {relative}')
        # Recheck the absolute target immediately before recursive removal.
        if output.resolve() != root or output.is_symlink() or output.is_junction():
            raise ValueError('work directory changed during verification')
        shutil.rmtree(output)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError, zlib.error, EOFError) as error:
        return replace(result, warnings=(*result.warnings,
            f'Work-directory cleanup did not complete ({error}). The ZIP is retained; remaining files are at {output}.'))
    if progress:
        progress('Verified ZIP retained; temporary conversion directory removed')
    return replace(result, work_directory_removed=True)
