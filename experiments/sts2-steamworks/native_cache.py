"""App-owned compiled cache, keyed by immutable sources, SDK and toolchain."""

import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile

from build_native import build, sdk_headers, SPINE_COMMIT, SPINE_CPP_COMMIT, SOURCE_COMMIT, GODOT_CPP_COMMIT, STEAM_API
from converter_io import read_verified, safe, write_new, publish_new
from convert_sts2 import load_profile, require_elf


def cached_build(cache,sdk,*,steam_api=STEAM_API,scons='scons'):
    cache=safe(cache);cache.mkdir(parents=True,exist_ok=True)
    headers=sdk_headers(sdk)
    profile=load_profile()
    vendor={}
    for item in profile['native_files']:
        name=item['provider_name']
        if name=='libsteam_api64.so': vendor[name]=read_verified(steam_api,item)
        elif name in ('libfmod.so.14','libfmodstudio.so.14'):
            section='core' if name=='libfmod.so.14' else 'studio'
            from build_native import sdk_file
            vendor[name]=read_verified(sdk_file(sdk,f'api/{section}/lib/arm64/{name}'),item)
    versions={tool:subprocess.check_output([str(tool),'--version'],text=True).splitlines()[:2] for tool in ('g++','git','readelf',scons)}
    recipe={'sources':[SPINE_COMMIT,SPINE_CPP_COMMIT,SOURCE_COMMIT,GODOT_CPP_COMMIT],
            'headers':{n:hashlib.sha256(raw).hexdigest() for n,raw in headers.items()},
            'vendor':{n:hashlib.sha256(raw).hexdigest() for n,raw in vendor.items()},
            'versions':{Path(k).name:v for k,v in versions.items()},'architecture':platform.machine(),'flags':['linux','arm64','template_release','SOURCE_DATE_EPOCH=1759276800']}
    key=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
    destination=cache/key
    if destination.exists():
        receipt=json.loads((destination/'receipt.json').read_bytes())
        if receipt.get('kind')!='megcfbt-compiled-source-cache-v1' or receipt['recipe']!=recipe: raise ValueError('Compiled cache provenance differs')
        evidence=receipt['evidence']
        if len(evidence['outputs'])!=5: raise ValueError('Compiled cache inventory differs')
        for item in profile['native_files']:
            name=item['provider_name'];pin=evidence['outputs'][name]
            raw=read_verified(destination/'native'/name,pin);require_elf(raw,name)
            if name in vendor and raw!=vendor[name]: raise ValueError('Cached vendor input differs')
            if 'spine' in name or 'GodotFmod' in name:
                symbol='spine_godot_library_init' if 'spine' in name else 'fmod_library_init'
                exports=subprocess.check_output(['readelf','--dyn-syms','--wide',str(destination/'native'/name)],text=True)
                if not any(line.split()[-1:]==[symbol] and ' UND ' not in line for line in exports.splitlines()): raise ValueError('Cached extension entry point missing')
                item.update(sha256=pin['sha256'],size_bytes=pin['size_bytes'])
        return destination/'native',profile,evidence
    staging=Path(tempfile.mkdtemp(prefix='.compile-',dir=cache))
    native,profile,evidence=build(staging/'work',sdk,steam_api=steam_api,scons=scons)
    write_new(staging/'receipt.json',(json.dumps({'kind':'megcfbt-compiled-source-cache-v1','recipe':recipe,'evidence':evidence},indent=2,sort_keys=True)+'\n').encode())
    # Keep only app-created artifacts/evidence at the cache publication root.
    (staging/'work/native').rename(staging/'native')
    publish_new(staging,destination)
    return destination/'native',profile,evidence
