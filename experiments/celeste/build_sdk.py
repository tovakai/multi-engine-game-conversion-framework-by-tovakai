"""Build a redistributable Celeste SDK on Linux ARM64 (FMOD stays owner supplied).

Requires git, GCC, CMake, make, SDL2 development files and .NET SDK 8 with the
8.0.31 runtime. Run with --work, --dotnet-sdk and --fmod-sdk paths. Native Steam
linking uses the Frame's installed client, which is never copied into the SDK.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

FNA_COMMIT = 'd0a0892f17dd8bebd36319294509cdca8ae8c810'
STEAM_COMMIT = '4dafa26fbd032c83c1970298cc93d66f47edfb59'
FMOD_SHA = '48241c836b45116e1b25f9f2cb121e45c64140c5af205706b48c8b1c3712f963'

def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): result.update(chunk)
    return result.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--dotnet-sdk', required=True, type=Path)
    parser.add_argument('--fmod-sdk', required=True, type=Path)
    args = parser.parse_args()
    if os.uname().machine not in {'aarch64', 'arm64'}:
        parser.error('Build on native Linux ARM64')
    work, dotnet = args.work.resolve(), args.dotnet_sdk.resolve()
    tools = Path(__file__).resolve().parent
    if sha(args.fmod_sdk) != FMOD_SHA:
        parser.error('The owner FMOD SDK must be the pinned 2.03.15 Linux archive')
    work.mkdir(parents=True, exist_ok=True)
    target = work/'runtime-sdk'
    if target.exists():
        parser.error('Use a new work directory; the SDK output already exists')
    environment = dict(os.environ, DOTNET_ROOT=str(dotnet), DOTNET_CLI_TELEMETRY_OPTOUT='1')
    environment['PATH'] = str(dotnet)+':'+environment['PATH']
    def run(*command, cwd=work):
        print('BUILD', *map(str, command), flush=True)
        subprocess.run(list(map(str, command)), cwd=cwd, env=environment, check=True)
    def checkout(name, url, tag, commit, submodules=False):
        path = work/name
        command = ['git', 'clone', '--depth', '1', '--branch', tag]
        if submodules: command.append('--recurse-submodules')
        run(*command, url, path)
        actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != commit: raise RuntimeError(f'{name} source commit mismatch')
        return path
    fna = checkout('FNA', 'https://github.com/FNA-XNA/FNA.git', '23.10', FNA_COMMIT, True)
    steam = checkout('Steamworks.NET', 'https://github.com/rlabrecque/Steamworks.NET.git', '20.0.0', STEAM_COMMIT)
    native = target/'native'
    managed = target/'managed'
    native.mkdir(parents=True)
    managed.mkdir()
    run(dotnet/'dotnet', 'build', fna/'FNA.Core.csproj', '-c', 'Release', '-f', 'netstandard2.0',
        '-p:TargetFrameworks=netstandard2.0', '-p:Platform=AnyCPU', '-p:PlatformTarget=AnyCPU')
    shutil.copy2(next((fna/'bin').rglob('FNA.dll')), managed/'FNA.dll')
    run(dotnet/'dotnet', 'build', tools/'steamworks/Steamworks.NET.csproj', '-c', 'Release',
        '-p:SteamworksSource='+str(steam), '-o', managed)
    for project in ['FNA3D', 'FAudio']:
        build = work/('build-'+project)
        run('cmake', '-S', fna/'lib'/project, '-B', build, '-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_POLICY_VERSION_MINIMUM=3.5')
        run('cmake', '--build', build, '-j', '4')
        for path in build.glob('lib'+project+'.so*'): shutil.copy2(path, native/path.name)
    run('make', '-j4', cwd=fna/'lib/Theorafile')
    shutil.copy2(fna/'lib/Theorafile/libtheorafile.so', native/'libtheorafile.so')
    for name in ['libSDL2.so', 'libSDL2-2.0.so.0']:
        shutil.copy2('/usr/lib/libSDL2-2.0.so.0', native/name)
    # Extract only the required headers and owner libraries into private build
    # inputs; neither the SDK nor its libraries are part of the public output.
    fmod = work/'owner-fmod'
    with tarfile.open(args.fmod_sdk) as archive:
        wanted = [member for member in archive.getmembers() if member.isfile() and
                  ('/api/core/inc/' in member.name or '/api/studio/inc/' in member.name or
                   member.name.endswith(('/arm64/libfmod.so.14.15', '/arm64/libfmodstudio.so.14.15')))]
        for member in wanted:
            relative = Path(*Path(member.name).parts[1:])
            if relative.is_absolute() or '..' in relative.parts: raise RuntimeError('Unsafe SDK path')
            destination = fmod/relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, destination.open('wb') as output:
                shutil.copyfileobj(source, output)
    owner_native = work/'owner-native'
    owner_native.mkdir()
    for directory, name in [('core', 'fmod'), ('studio', 'fmodstudio')]:
        shutil.copy2(fmod/f'api/{directory}/lib/arm64/lib{name}.so.14.15', owner_native/f'lib{name}.so.14')
    run('gcc', '-shared', '-fPIC', '-O2', tools/'native/fmod_compat.c',
        '-I'+str(fmod/'api/core/inc'), '-I'+str(fmod/'api/studio/inc'), '-L'+str(owner_native),
        '-Wl,--no-as-needed', '-Wl,-rpath,$ORIGIN', '-l:libfmodstudio.so.14', '-l:libfmod.so.14',
        '-ldl', '-o', native/'libceleste_fmod_compat.so')
    framework = tools.parents[1]
    guard = framework/'megcfbt/runtime_support/libframe_steam_env.so'
    if not guard.is_file(): raise RuntimeError('Framework ARM64 Steam graphics guard missing')
    shutil.copy2(guard, native/guard.name)
    run('gcc', '-shared', '-fPIC', '-O2', tools/'native/steam_legacy_bridge.c', tools/'native/steam_init.c',
        '-L'+str(native), '-L/opt/steamvr/bin/linuxarm64', '-Wl,--no-as-needed',
        '-lframe_steam_env', '-lsteam_api', '-ldl', '-Wl,-rpath,$ORIGIN', '-o', native/'libsteam_api64.so')
    run(dotnet/'dotnet', 'publish', tools/'prepare/CelestePrepare.csproj', '-c', 'Release',
        '-o', target/'prepare/managed', '-p:UseAppHost=false')
    run(dotnet/'dotnet', 'publish', tools/'prepare/CelestePrepare.csproj', '-c', 'Release',
        '-r', 'win-x64', '--self-contained', 'true', '-p:PublishSingleFile=true',
        '-p:IncludeNativeLibrariesForSelfExtract=true', '-o', target/'prepare/windows-x64')
    (target/'dotnet').mkdir()
    shutil.copy2(dotnet/'dotnet', target/'dotnet/dotnet')
    for directory in ['host/fxr', 'shared/Microsoft.NETCore.App']:
        shutil.copytree(dotnet/directory/'8.0.31', target/'dotnet'/directory/'8.0.31')
    licenses = target/'licenses'
    licenses.mkdir()
    sources = [fna/'licenses', fna/'lib/Theorafile/licenses']
    for directory in sources:
        for path in directory.iterdir():
            if path.is_file(): shutil.copy2(path, licenses/(directory.parent.name+'-'+path.name))
    for path, name in [(fna/'lib/FNA3D/LICENSE', 'FNA3D-LICENSE'), (fna/'lib/FAudio/LICENSE', 'FAudio-LICENSE'),
        (fna/'lib/FNA3D/MojoShader/LICENSE.txt', 'MojoShader-LICENSE.txt'),
        (fna/'lib/SDL2-CS/LICENSE', 'SDL2-CS-LICENSE'), (steam/'LICENSE.txt', 'Steamworks.NET-LICENSE.txt'),
        (Path('/usr/share/licenses/sdl2/LICENSE'), 'SDL2-LICENSE'),
        (dotnet/'LICENSE.txt', 'DotNet-LICENSE.txt'), (dotnet/'ThirdPartyNotices.txt', 'DotNet-ThirdPartyNotices.txt'),
        (tools/'licenses/Mono.Cecil-LICENSE.txt', 'Mono.Cecil-LICENSE.txt'),
        (tools/'licenses/FMODStudioFix-MIT.txt', 'FMODStudioFix-MIT.txt'), (framework/'LICENSE', 'Framework-LICENSE')]:
        shutil.copy2(path, licenses/name)
    shutil.copytree(tools/'native', target/'source/native')
    shutil.copy2(framework/'megcfbt/runtime_support/frame_steam_env.c', target/'source/native/frame_steam_env.c')
    shutil.copytree(tools/'prepare', target/'source/prepare', ignore=shutil.ignore_patterns('bin', 'obj'))
    shutil.copy2(Path(__file__), target/'source/build_sdk.py')
    provenance = {'FNA': FNA_COMMIT, 'Steamworks.NET': STEAM_COMMIT,
        'dotnet': '8.0.31', 'SDL2': subprocess.check_output(['pkg-config', '--modversion', 'sdl2'], text=True).strip(),
        'fmod_sdk_header_sha256': FMOD_SHA, 'vendor_libraries_distributed': False}
    (target/'source/provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    files = {path.relative_to(target).as_posix(): sha(path) for path in target.rglob('*') if path.is_file()}
    runtime_files = [name for name in files if not name.startswith(('prepare/', 'source/'))]
    manifest = {'schema': 1, 'profile': 'celeste-steam-xna-1.4.0.0', 'architecture': 'aarch64',
        'recipe_id': 'celeste-steam-xna-1-4-0-0-net8-fna2310', 'dotnet_version': '8.0.31',
        'files': files, 'runtime_files': runtime_files}
    (target/'engine-capabilities.json').write_text(json.dumps(manifest, indent=2)+'\n')
    output = work/'celeste-steam-xna-1-4-0-0-net8-fna2310.tar.gz'
    with tarfile.open(output, 'w:gz') as archive:
        for path in target.rglob('*'):
            if path.is_file(): archive.add(path, arcname=path.relative_to(target).as_posix())
    print(output, sha(output), flush=True)

if __name__ == '__main__': main()
