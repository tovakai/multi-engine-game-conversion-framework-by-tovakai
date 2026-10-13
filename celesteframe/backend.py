"""Convert the verified Windows XNA Celeste edition to Linux ARM64 FNA."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from celesteframe.profiles import PROFILE, matches_source
from celesteframe.runtime import resolve_runtime, copy_runtime, find_fmod_sdk, validate_sdk, validate_fmod_sdk
from megcfbt.models import UnifiedInspection
from megcfbt.native_backend import NativeBuildError, build_native

def inspect_game(root: Path):
    if not (root/'Celeste.exe').is_file() or not (root/'Content/FMOD').is_dir():
        return None
    known = matches_source(root)
    return UnifiedInspection(root, 'celesteframe', 'fna', 'Celeste / XNA to FNA',
        '1.4.0.0' if known else None, 'Celeste', 'needs_testing' if known else 'unsupported',
        'high', PROFILE if known else 'celeste-profile-required', known,
        warnings=('Requires the matching Celeste SDK and owner-supplied FMOD Studio API 2.03.15 Linux SDK.',
                  'Use a Steam shortcut and select the primary controller in Steam; mods and Everest are unsupported.'),
        evidence=('Celeste.exe', 'Content/FMOD') + (('Pinned vanilla Steam Windows XNA assembly identities',) if known else ()))

def write_managed_config(target: Path, dotnet_version: str):
    (target/'Celeste.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {
        'tfm': 'net8.0', 'framework': {'name': 'Microsoft.NETCore.App', 'version': dotnet_version}}}, indent=2)+'\n')
    framework = '.NETCoreApp,Version=v8.0'
    dependencies = {'FNA': '23.10.0', 'Steamworks.NET': '20.0.0'}
    entries = {'Celeste/1.0.0': {'dependencies': dependencies, 'runtime': {'Celeste.exe': {}}}}
    libraries = {'Celeste/1.0.0': {'type': 'project', 'serviceable': False, 'sha512': ''}}
    for name, version in dependencies.items():
        entries[f'{name}/{version}'] = {'runtime': {f'{name}.dll': {}}}
        libraries[f'{name}/{version}'] = {'type': 'project', 'serviceable': False, 'sha512': ''}
    (target/'Celeste.deps.json').write_text(json.dumps({'runtimeTarget': {'name': framework, 'signature': ''},
        'compilationOptions': {}, 'targets': {framework: entries}, 'libraries': libraries}, indent=2)+'\n')

def build_game(source: Path, *, output: Path, runtime=None, runtime_version=None, force=False,
               progress=None, download_progress=None, steam_app_id=None, fmod_sdk=None):
    source = Path(source).resolve()
    if not matches_source(source):
        raise NativeBuildError('Expected the verified vanilla Steam Windows XNA Celeste 1.4.0.0 installation; mods, Everest and other editions need a separate profile.')
    if runtime_version not in (None, '1.4.0.0'):
        raise NativeBuildError('Celeste requires the pinned 1.4.0.0 source profile.')
    try:
        fmod = validate_fmod_sdk(Path(fmod_sdk)) if fmod_sdk else find_fmod_sdk()
    except RuntimeError as error:
        raise NativeBuildError(str(error)) from error
    if fmod is None:
        raise NativeBuildError('Celeste needs the separately obtained FMOD Studio API 2.03.15 Linux SDK. Place fmodstudioapi20315linux.tar.gz in Downloads or set MEGCFBT_CELESTE_FMOD_SDK.')
    sdk = resolve_runtime(runtime, progress=progress, download_progress=download_progress)
    manifest = validate_sdk(sdk)
    if force and Path(output).exists() and any((Path(output)/name).exists() for name in ('game/Saves', 'userdata', 'userconfig')):
        raise NativeBuildError('This Celeste output contains user data; select a new output directory to preserve it.')
    def prepare(target):
        target.mkdir()
        shutil.copytree(source/'Content', target/'Content')
        if (source/'Saves').is_dir():
            shutil.copytree(source/'Saves', target/'Saves')
        shutil.copy2(sdk/'managed/FNA.dll', target/'FNA.dll')
        if sys.platform == 'win32':
            command = [str(sdk/'prepare/windows-x64/CelestePrepare.exe')]
        elif sys.platform.startswith('linux'):
            command = [str(sdk/'dotnet/dotnet'), str(sdk/'prepare/managed/CelestePrepare.dll')]
        else:
            raise NativeBuildError('Celeste preparation supports Windows x64 and Linux ARM64 hosts.')
        command += [str(source/'Celeste.exe'), str(sdk/'managed/FNA.dll'),
                    str(sdk/'managed/Steamworks.NET.dll'), str(target/'Celeste.exe')]
        environment = dict(os.environ, DOTNET_ROOT=str(sdk/'dotnet'))
        completed = subprocess.run(command, env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        if completed.returncode:
            raise NativeBuildError('Celeste managed preparation failed: '+completed.stdout[-4000:])
        if progress:
            for line in completed.stdout.splitlines(): progress(line)
        write_managed_config(target, manifest['dotnet_version'])
    return build_native(source, output=output, runtime=sdk, executable='dotnet/dotnet',
        engine='CelesteFrame', game_name='Celeste', engine_version='1.4.0.0', prepare_game=prepare,
        arguments=['Celeste.exe'], force=force, progress=progress, steam_app_id='504230',
        compatibility_profile=PROFILE,
        prepare_runtime=lambda root, target: copy_runtime(root, target, fmod),
        launcher_environment='export DOTNET_ROOT="$ROOT/runtime/dotnet"\n'
            'export LD_LIBRARY_PATH="$ROOT/runtime/native:/opt/steamvr/bin/linuxarm64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\n'
            'export SteamAppId=504230\n'
            'export FNA3D_FORCE_DRIVER=Vulkan\n'
            'export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-x11}"\n'
            'export XDG_DATA_HOME="$ROOT/userdata"\n'
            'export XDG_CONFIG_HOME="$ROOT/userconfig"\n',
        warnings=('Experimental Celeste profile; use a Steam shortcut with the desired primary controller. Full-game completion, achievements and Steam Cloud remain unverified.',))
