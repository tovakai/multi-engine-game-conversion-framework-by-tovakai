"""Shared verified download and atomic installation for flat runtime bundles."""
from pathlib import Path
import hashlib,shutil,tarfile,tempfile,urllib.error,urllib.request


class RuntimeDownloadError(RuntimeError):
    pass


def ensure_bundle(entry: dict, target: Path, *, validate, progress=None, download_progress=None) -> Path:
    if validate(target):
        if progress:progress('Using cached verified ARM64 runtime')
        return target
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.runtime-',dir=target.parent) as temporary:
        work=Path(temporary);archive=work/'runtime.tar.gz';stage=work/'extracted';stage.mkdir()
        digest=hashlib.sha256();received=0
        if progress:progress('Downloading native ARM64 runtime…')
        try:
            with urllib.request.urlopen(entry['url'],timeout=45) as response,archive.open('wb') as output:
                size=response.headers.get('Content-Length')
                total=int(size) if size and size.isdigit() else None
                while chunk:=response.read(1024*1024):
                    received+=len(chunk)
                    if received>2*1024**3:raise RuntimeDownloadError('Runtime download exceeds 2 GiB limit')
                    output.write(chunk);digest.update(chunk)
                    if download_progress:download_progress(received,total)
        except (OSError,urllib.error.URLError) as exc:
            raise RuntimeDownloadError(f'Could not download native runtime: {exc}') from exc
        if progress:progress('Verifying native runtime SHA-256…')
        if digest.hexdigest()!=entry['sha256'].lower():
            raise RuntimeDownloadError('Runtime download SHA-256 mismatch; refusing to use it')
        allowed=set(entry['archive_files']);seen=set()
        try:
            with tarfile.open(archive,'r:*') as tar:
                for member in tar:
                    if not member.isfile() or member.name not in allowed or member.name in seen:
                        raise RuntimeDownloadError(f'Unsafe or unexpected runtime archive member: {member.name}')
                    if member.size>512*1024**2:raise RuntimeDownloadError('Runtime member exceeds 512 MiB limit')
                    seen.add(member.name);stream=tar.extractfile(member)
                    if stream is None:raise RuntimeDownloadError('Unreadable runtime archive member')
                    with stream,(stage/member.name).open('wb') as destination:shutil.copyfileobj(stream,destination)
            if seen!=allowed:raise RuntimeDownloadError('Runtime archive is missing required files')
        except (OSError,tarfile.TarError,EOFError) as exc:
            raise RuntimeDownloadError(f'Could not unpack verified runtime archive: {exc}') from exc
        if not validate(stage):raise RuntimeDownloadError('Runtime failed ARM64 architecture, recipe or file integrity validation')
        (stage/entry['executable']).chmod(0o755)
        backup=work/'previous'
        try:
            if target.exists():target.rename(backup)
            stage.rename(target)
        except OSError as exc:
            if backup.exists() and not target.exists():backup.rename(target)
            raise RuntimeDownloadError(f'Could not install verified runtime cache: {exc}') from exc
    if progress:progress('Native ARM64 runtime verified and cached')
    return target
