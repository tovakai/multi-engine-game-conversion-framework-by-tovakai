"""Reproducible native ARM64 SDK builds for the data-driven backends.

Run on Linux ARM64 with the documented CMake/SDL/media development packages,
optionally inside an existing distrobox. This never installs host packages.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from megcfbt.native_backend import validate_runtime, NativeBuildError
from rpgmframe.steam_sdk_compat import normalize_proton_headers
from rpgmframe.godot_custom_runtime import PROTON_REF, _distrobox_command

SOURCES = {
    'gamemaker': ('ButterscotchRunner/Butterscotch','fcc295961097b801e24f3dd2f9a41851db899ac2'),
    'love': ('love2d/love','6eb8d546736d5915a8b5af30b2cf33456dfdcb1a'),
    'https': ('love2d/lua-https','e1b77046dd3cf1a9f61ddeb63cb39d47c844c089'),
    'luasteam': ('uspgamedev/luasteam','18bfe7bad7f167555ac5bf6df6ef23883a57fcfe'),
    'ags': ('adventuregamestudio/ags','810192970bfa8859041bca6f50ff6d9eba190036'),
}


def build_sdk(engine: str, *, output: Path, work_dir: Path, distrobox: str | None = None,
              steam_api: Path | None = None, progress=print) -> Path:
    if platform.system() != 'Linux' or platform.machine().casefold() not in {'aarch64','arm64'}:
        raise NativeBuildError('SDK source builds require Linux ARM64; use a prepared bundle on Windows.')
    output, work_dir = output.expanduser().resolve(),work_dir.expanduser().resolve()
    if output == work_dir or output in work_dir.parents or work_dir in output.parents:
        raise NativeBuildError('SDK output and build workspace must be separate directories.')
    if output.exists():
        raise NativeBuildError(f'SDK output already exists: {output}')
    work_dir.mkdir(parents=True,exist_ok=True)
    box = _distrobox_command() if distrobox else None
    if distrobox and not box:
        raise NativeBuildError('Requested distrobox is unavailable.')
    prefix = [box,'enter',distrobox,'--'] if box else []
    def run(args):
        progress(' '.join(str(arg) for arg in args))
        subprocess.run(prefix+[str(arg) for arg in args],check=True)
    def clone(name):
        repo,ref = SOURCES[name]
        path = work_dir/name
        if not path.exists():
            run(['git','init',path])
            run(['git','-C',path,'remote','add','origin','https://github.com/'+repo+'.git'])
            run(['git','-C',path,'fetch','--depth','1','origin',ref])
            run(['git','-C',path,'checkout','--detach','FETCH_HEAD'])
        actual = subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
        if len(ref) == 40 and actual != ref:
            raise NativeBuildError(f'Source commit mismatch for {name}')
        return path
    def cmake(name,source,options=()):
        build = work_dir/(name+'-build')
        run(['cmake','-S',source,'-B',build,'-DCMAKE_BUILD_TYPE=Release',*options])
        run(['cmake','--build',build,'--parallel',str(min(6,os.cpu_count() or 1))])
        return build
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.native-sdk-',dir=output.parent) as temporary:
        stage = Path(temporary)/'sdk'
        stage.mkdir()
        source = clone(engine)
        if engine == 'gamemaker':
            patch = Path(__file__).resolve().parent.parent/'gamemakerframe/patches/butterscotch-ds-list-set-arity.patch'
            applied = subprocess.run(['git','-C',str(source),'apply','--reverse','--check',str(patch)],capture_output=True).returncode == 0
            if not applied:
                run(['git','-C',source,'apply',patch])
            build = cmake(engine,source,['-DBACKEND=sdl2'])
            shutil.copy2(build/'butterscotch',stage/'butterscotch')
            shutil.copy2(source/'LICENSE',stage/'LICENSE-Butterscotch.txt')
            capabilities = {'steam_support':'offline-stubs','patches':['ds-list-set-arity']}
            executable = 'butterscotch'
        elif engine == 'ags':
            build = cmake(engine,source,['-DAGS_USE_LOCAL_SDL2=ON','-DAGS_USE_LOCAL_OGG=ON',
                                        '-DAGS_USE_LOCAL_THEORA=ON','-DAGS_USE_LOCAL_VORBIS=ON','-DAGS_BUILTIN_PLUGINS=ON'])
            shutil.copy2(build/'ags',stage/'ags')
            shutil.copy2(source/'License.txt',stage/'LICENSE-AGS.txt')
            capabilities = {'builtin_plugins':['agsblend','agsflashlight','agsparallax','agspalrender'],
                            'stub_plugins':['agsteam','agsteam-unified','agsteam-disjoint'], 'engine_version':'3.6.2.21'}
            executable = 'ags'
        elif engine == 'love':
            build = cmake(engine,source,['-DCMAKE_BUILD_RPATH_USE_ORIGIN=ON'])
            https = clone('https')
            https_build = cmake('https',https)
            lua = clone('luasteam')
            api = (steam_api or Path('/opt/steamvr/bin/linuxarm64/libsteam_api.so')).resolve()
            from renframe.elf import read_elf_architecture
            if read_elf_architecture(api) != 'aarch64':
                raise NativeBuildError('LÖVE Steam bindings require an ARM64 Steam API library (--steam-api).')
            proton = work_dir/'proton'
            if not proton.exists():
                run(['git','clone','--filter=blob:none','--no-checkout','https://github.com/ValveSoftware/Proton.git',proton])
                run(['git','-C',proton,'sparse-checkout','init','--cone'])
                run(['git','-C',proton,'sparse-checkout','set','lsteamclient/steamworks_sdk_162'])
                run(['git','-C',proton,'fetch','--depth','1','origin',PROTON_REF])
                run(['git','-C',proton,'checkout','--detach','FETCH_HEAD'])
            actual = subprocess.check_output(['git','-C',str(proton),'rev-parse','HEAD'],text=True).strip()
            if actual != PROTON_REF:
                raise NativeBuildError('Proton SDK source commit mismatch.')
            headers = lua/'sdk/public/steam'
            if not headers.exists():
                shutil.copytree(proton/'lsteamclient/steamworks_sdk_162',headers)
                normalize_proton_headers(headers)
            lib = lua/'sdk/redistributable_bin/linux64/libsteam_api.so'
            lib.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(api,lib)
            stats = lua/'src/user_stats.cpp'
            text = stats.read_text().replace('SteamUserStats()->RequestCurrentStats()',
                    'SteamUserStats()->RequestUserStats(SteamUser()->GetSteamID()) != k_uAPICallInvalid')
            stats.write_text(text)
            run(['make','-C',lua,'linux64','GNU_IPATHS=-I/usr/include/luajit-2.1'])
            for path in [build/'love',build/'libliblove.so',https_build/'src/https.so',lua/'luasteam.so',lib]:
                shutil.copy2(path,stage/path.name)
            shutil.copy2(source/'license.txt',stage/'LICENSE-LOVE.txt')
            shutil.copy2(lua/'LICENSE',stage/'LICENSE-luasteam.txt')
            shutil.copy2(https/'license.txt',stage/'LICENSE-lua-https.txt')
            capabilities = {'engine_version':'11.5','lua_abi':'LuaJIT/Lua 5.1','native_modules':['https','luasteam'],
                            'steam_headers':'Proton Steamworks 1.62', 'patches':['request-current-stats-compat','native-networking-helpers']}
            executable = 'love'
        else:
            raise NativeBuildError(f'Unknown SDK engine: {engine}')
        capabilities.update({'recipe_id':engine+'-arm64-sdk-v1','architecture':'aarch64',
                             'source':SOURCES[engine][0],'source_ref':SOURCES[engine][1]})
        (stage/'engine-capabilities.json').write_text(json.dumps(capabilities,indent=2)+'\n',encoding='utf-8')
        validate_runtime(stage,executable)
        stage.rename(output)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('engine',choices=['gamemaker','love','ags'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--distrobox')
    parser.add_argument('--steam-api',type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_sdk(args.engine,output=args.output,work_dir=args.work_dir,distrobox=args.distrobox,steam_api=args.steam_api)
    except (NativeBuildError,OSError,subprocess.CalledProcessError,ValueError) as exc:
        parser.exit(2,f'ERROR: {exc}\n')
    print('SDK ready:',result)


if __name__ == '__main__':
    main()
