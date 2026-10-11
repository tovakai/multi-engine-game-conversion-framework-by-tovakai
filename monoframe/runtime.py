"""Checksum-pinned nested SDKs containing ARM64 runtime and host preparation tools."""
from pathlib import Path,PurePosixPath
import hashlib,json,os,re,shutil,struct
from megcfbt.native_backend import NativeBuildError,validate_runtime
from megcfbt.native_runtime import _cache_parent
from megcfbt.runtime_download import ensure_bundle,RuntimeDownloadError
from renframe.elf import read_elf_architecture
from monoframe.profiles import STARDEW_PROFILE

INDEX_PATH=Path(__file__).with_name('runtime_index.json')


def windows_x64_executable(path: Path) -> bool:
    try:
        with path.open('rb') as stream:
            header=stream.read(64)
            if len(header)<64 or header[:2]!=b'MZ':return False
            stream.seek(struct.unpack_from('<I',header,60)[0]);pe=stream.read(6)
            return pe[:4]==b'PE\0\0' and len(pe)==6 and struct.unpack_from('<H',pe,4)[0]==0x8664
    except (OSError,struct.error):return False


def recipe_entry(profile=STARDEW_PROFILE):
    try:entry=json.loads(INDEX_PATH.read_text())['recipes'][profile]
    except (OSError,ValueError,KeyError,TypeError):return None
    if (not isinstance(entry,dict) or entry.get('executable')!='dotnet/dotnet'
        or not str(entry.get('url','')).startswith('https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/')
        or not re.fullmatch('[0-9a-f]{64}',str(entry.get('sha256','')))
        or not re.fullmatch('[a-z0-9-]+',str(entry.get('recipe_id','')))):return None
    files=entry.get('archive_files')
    if not isinstance(files,list) or not files or not all(isinstance(name,str) for name in files) or len(files)!=len(set(files)):return None
    for name in files:
        if not isinstance(name,str) or PurePosixPath(name).is_absolute() or any(part in {'.','..'} or not re.fullmatch('[A-Za-z0-9_+.-]+',part) or part.endswith('.') for part in name.split('/')):return None
    if not {'dotnet/dotnet','engine-capabilities.json','prepare/windows-x64/MainlineGameDataPatcher.exe'}.issubset(files):return None
    return entry


def automatic_runtime_available():return recipe_entry() is not None


def validate_sdk(root: Path,entry=None):
    try:
        validate_runtime(root,'dotnet/dotnet')
        if not windows_x64_executable(root/'prepare/windows-x64/MainlineGameDataPatcher.exe'):return False
        manifest=json.loads((root/'engine-capabilities.json').read_text())
        if manifest.get('profile')!=STARDEW_PROFILE or manifest.get('architecture')!='aarch64':return False
        if entry and manifest.get('recipe_id')!=entry['recipe_id']:return False
        files=manifest['files']
        if not isinstance(files,dict) or not files:return False
        if entry and set(files)!=set(entry['archive_files'])-{'engine-capabilities.json'}:return False
        for name,digest in files.items():
            if not isinstance(name,str) or not re.fullmatch('[0-9a-f]{64}',str(digest)):return False
            if PurePosixPath(name).is_absolute() or any(p in {'.','..'} for p in name.split('/')) or '\\' in name or ':' in name:return False
            path=root/name
            if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:return False
            if name.startswith('native/') and name.endswith(('.so','.dll')) and read_elf_architecture(path)!='aarch64':return False
        return bool(manifest.get('runtime_files') and set(manifest['runtime_files']).issubset(files))
    except (OSError,ValueError,KeyError,TypeError,NativeBuildError):return False


def resolve_runtime(runtime=None,*,progress=None,download_progress=None):
    if runtime is not None or os.environ.get('MONOFRAME_RUNTIME'):
        selected=Path(runtime or os.environ['MONOFRAME_RUNTIME']).expanduser().resolve()
        if not validate_sdk(selected):raise NativeBuildError('MonoFrame SDK failed architecture/profile/file validation.')
        return selected
    entry=recipe_entry()
    if entry is None:raise NativeBuildError('No published MonoFrame runtime for this source profile; select a matching SDK.')
    target=_cache_parent()/'monoframe'/entry['recipe_id']
    try:return ensure_bundle(entry,target,validate=lambda path:validate_sdk(path,entry),progress=progress,download_progress=download_progress)
    except RuntimeDownloadError as error:raise NativeBuildError(str(error)) from error


def copy_game_runtime(sdk: Path,target: Path):
    manifest=json.loads((sdk/'engine-capabilities.json').read_text())
    target.mkdir()
    selected=manifest['runtime_files']
    for name in selected:
        dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(sdk/name,dest)
    manifest['files']={name:manifest['files'][name] for name in selected}
    manifest['purpose']='game-runtime'
    (target/'engine-capabilities.json').write_text(json.dumps(manifest,indent=2)+'\n')
