"""Native managed-game conversion using a versioned .NET/MonoGame SDK."""
from pathlib import Path
from dataclasses import replace
import json,os,shutil,subprocess,sys
from megcfbt.models import UnifiedInspection
from megcfbt.native_backend import NativeBuildError,build_native
from monoframe.profiles import matches_stardew,STARDEW_PROFILE
from monoframe.runtime import resolve_runtime,copy_game_runtime
from monoframe.preparation import preparation_command


def inspect_game(root: Path):
    from monoframe import celeste
    inspection = celeste.inspect_game(root)
    if inspection is not None:
        return replace(inspection, backend='monoframe')
    framework=root/'MonoGame.Framework.dll'
    if not framework.is_file():return None
    try:
        with framework.open('rb') as stream:
            if stream.read(2)!=b'MZ':return None
    except OSError:return None
    known=matches_stardew(root)
    return UnifiedInspection(source_path=root,backend='monoframe',engine='monogame',
        engine_label='MonoGame / .NET',engine_version='3.8.0.1641' if known else None,
        game_name='Stardew Valley' if known else root.name,
        compatibility='needs_testing' if known else 'unsupported',confidence='high',
        runtime_kind=STARDEW_PROFILE if known else 'monoframe-profile-required',buildable=known,
        evidence=('MonoGame.Framework.dll',)+(('Steam Stardew 1.6.15.24356 / .NET 6.0.32; pinned assembly identities',) if known else ()),
        warnings=('Experimental native .NET/MonoGame conversion; validate gameplay, input, audio and saves.',) if known else
            ('This MonoGame installation needs a supported source/runtime profile. Modified, SMAPI and unrecognized Stardew releases are not automatically converted.',))


def build_game(source: Path,*,output: Path,runtime=None,runtime_version=None,force=False,progress=None,download_progress=None,steam_app_id=None,fmod_sdk=None):
    source = Path(source).resolve()
    from monoframe import celeste
    if celeste.inspect_game(source) is not None:
        return celeste.build_game(source, output=output, runtime=runtime,
            runtime_version=runtime_version, force=force, progress=progress,
            download_progress=download_progress, steam_app_id=steam_app_id, fmod_sdk=fmod_sdk)
    if not matches_stardew(source):raise NativeBuildError('Unsupported or modified MonoFrame source; expected the pinned vanilla Steam Stardew Valley installation.')
    sdk=resolve_runtime(runtime,progress=progress,download_progress=download_progress)
    def prepare(target):
        shutil.copytree(source,target)
        command=preparation_command(sdk, 'MainlineGameDataPatcher')
        command += ['--game-dir',str(target),'--overlay-dir',str(sdk/'managed')]
        if progress:progress('Preparing managed game assemblies in the converted copy')
        env=os.environ.copy();env['DOTNET_ROOT']=str(sdk/'dotnet')
        if sys.platform.startswith('linux'):env['DOTNET_ROOT']=str(Path(command[0]).resolve().parent)
        result=subprocess.run(command,cwd=target,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,encoding='utf-8',errors='replace',timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        if result.returncode:raise NativeBuildError('Managed preparation failed: '+result.stdout[-4000:])
        if progress:
            for line in result.stdout.splitlines():progress(line)
        (target/'MONOFRAME-PROFILE.json').write_text(json.dumps({'profile':STARDEW_PROFILE,
            'original_installation_modified':False,'engine':'.NET 6.0.32 / MonoGame 3.8.0.1641',
            'smapi':False,'gameplay_verification':'pending'},indent=2)+'\n')
    return build_native(source,output=output,runtime=sdk,executable='dotnet/dotnet',
        engine='MonoFrame',game_name='Stardew Valley',engine_version='3.8.0.1641',
        runtime_version='3.8.0.1641', game_version='1.6.15', compatibility_profile=STARDEW_PROFILE,
        prepare_game=prepare,arguments=['Stardew Valley.dll'],force=force,progress=progress,
        steam_app_id=steam_app_id or '413150',prepare_runtime=copy_game_runtime,
        launcher_environment='export DOTNET_ROOT="$ROOT/runtime/dotnet"\n'
            'export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"\n'
            'mkdir -p "$XDG_CONFIG_HOME" || exit 1\n'
            'export LD_LIBRARY_PATH="$ROOT/runtime/native:/opt/steamvr/bin/linuxarm64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\n',
        warnings=('Experimental MonoFrame profile; SMAPI, Steam online features and full gameplay remain unverified.',))
