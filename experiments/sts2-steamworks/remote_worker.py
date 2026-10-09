"""Private Frame jobs: verified uploads, safe extraction and the existing pipeline."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import time

from converter_io import safe, relative, read_verified, verified_stream, write_new, publish_new
from convert_sts2 import load_profile, create_tar
from sdk_archive import PIN as SDK_PIN
from build_native import STEAM_API


def emit(kind, **data):
    print(json.dumps({"type": kind, **data}), flush=True)


def job_root(value):
    root = safe(value)
    marker = json.loads((root / "job.json").read_bytes())
    if marker.get("kind") != "megcfbt-sts2-job-v1" or root.name != "job-" + marker["id"]:
        raise ValueError("Not an application-owned job directory")
    return root


def probe(base):
    base = safe(base)
    parent = base
    while not parent.exists():
        parent = parent.parent
    report = {"architecture": platform.machine(), "python": sys.version.split()[0],
              "free_bytes": shutil.disk_usage(parent).free,
              "writable": os.access(parent, os.W_OK), "tools": {}, "sdk_candidates": []}
    for name in ("git", "g++", "readelf"):
        executable = shutil.which(name)
        report["tools"][name] = executable
    report["venv_available"] = bool(__import__('importlib.util', fromlist=['find_spec']).find_spec('venv'))
    try:
        profile = load_profile()
        pin = next(p for p in profile["native_files"] if p["provider_name"] == "libsteam_api64.so")
        read_verified(STEAM_API, pin)
        report["valve_api_verified"] = True
    except (OSError, ValueError):
        report["valve_api_verified"] = False
    runtime = Path.home()/'.local/share/Steam/steamapps/common/SteamLinuxRuntime_4/pressure-vessel-arm64/bin/pressure-vessel-unruntime'
    report["valve_host_runtime"] = runtime.is_file() and os.access(runtime, os.X_OK)
    for directory in (Path.home()/"Downloads", base/"cache/vendor"):
        candidate = directory / "fmodstudioapi20315linux.tar.gz"
        if candidate.is_file():
            try:
                with verified_stream(candidate, SDK_PIN): pass
                report["sdk_candidates"].append(str(candidate))
            except (OSError, ValueError): pass
    emit("result", **report)


def transfer_status(root, name):
    root = job_root(root)
    if name not in {"source.tar", "sdk.tar.gz"}: raise ValueError("Unsupported transfer")
    path = root / (name + ".part")
    digest = hashlib.sha256()
    size = 0
    if path.exists():
        safe(path)
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                size += len(block); digest.update(block)
    complete=root/name
    final=None
    if complete.exists():
        safe(complete)
        with complete.open('rb') as stream: final={'size':complete.stat().st_size,'sha256':hashlib.file_digest(stream,'sha256').hexdigest()}
    emit("result", offset=size, prefix_sha256=digest.hexdigest(), complete=final)


def upload(root, name, size, digest, offset):
    root = job_root(root)
    if name not in {"source.tar", "sdk.tar.gz"} or size < 0 or size > 8*1024**3: raise ValueError("Invalid upload")
    partial = safe(root / (name + ".part"))
    if partial.exists():
        if partial.stat().st_size != offset: raise ValueError("Upload offset changed")
        stream = partial.open('ab')
    else:
        if offset: raise ValueError("Missing partial upload")
        stream = partial.open('xb')
    with stream:
        remaining = size-offset
        while remaining:
            block = sys.stdin.buffer.read(min(1024*1024, remaining))
            if not block: raise ValueError("Interrupted upload; partial file retained")
            stream.write(block); remaining -= len(block)
        stream.flush(); os.fsync(stream.fileno())
    with verified_stream(partial, {"size_bytes": size, "sha256": digest}): pass
    publish_new(partial, root/name)
    emit("result", verified=True, bytes=size)


def reuse_input(root,name,size,digest):
    root=job_root(root)
    if name not in {'source.tar','sdk.tar.gz'} or size < 0 or size > 8*1024**3:
        raise ValueError('Invalid reusable input')
    destination=root/name
    if destination.exists() or (root/(name+'.part')).exists():
        emit('result',reused=False);return
    # Only application-owned original-input transfers are eligible. Never inspect
    # converted outputs, prototypes or unrelated installations.
    for candidate in sorted(root.parent.glob('job-*')):
        if candidate==root: continue
        try:
            candidate=job_root(candidate)
            source=safe(candidate/name)
            if not source.is_file() or source.stat().st_size!=size: continue
            with verified_stream(source,{'size_bytes':size,'sha256':digest}): pass
            os.link(source,destination) # no overwrite; extraction revalidates every input
            emit('result',reused=True);return
        except (OSError,ValueError,KeyError): continue
    emit('result',reused=False)


def extract_source(root):
    destination = root/'source'
    if destination.exists(): return destination
    with tarfile.open(root/'source.tar','r:') as package:
        member=package.getmember('release_info.json')
        if not member.isfile() or member.size>4096: raise ValueError('Invalid source release metadata')
        metadata=json.loads(package.extractfile(member).read())
    profile = load_profile()
    if (metadata.get('version'),metadata.get('commit'))==('v0.107.1','59260271'):
        profile=json.loads((Path(__file__).parent/'converter_profile_v107.json').read_bytes())
    expected = {p['source']:p for p in profile['copy_files']}
    expected.update({'data_sts2_windows_x86_64/'+n:p for n,p in profile['managed_inputs'].items()})
    expected['SlayTheSpire2.pck'] = profile['pack']
    temporary = root/'source-staging'
    if temporary.exists():
        raise ValueError("Incomplete source extraction retained; choose a new job")
    temporary.mkdir(mode=0o700)
    with tarfile.open(root/'source.tar','r:') as archive:
        members = archive.getmembers()
        if len(members) != len(expected) or {p.name for p in members} != set(expected):
            raise ValueError("Unexpected source archive inventory")
        for member in members:
            pin = expected[member.name]
            if not member.isfile() or member.size != pin['size_bytes']: raise ValueError("Invalid source member")
            path = temporary/relative(member.name)
            path.parent.mkdir(parents=True,exist_ok=True)
            digest=hashlib.sha256()
            with archive.extractfile(member) as inp, path.open('xb') as out:
                for block in iter(lambda: inp.read(1024*1024), b''):
                    digest.update(block); out.write(block)
            if digest.hexdigest()!=pin['sha256']: raise ValueError("Source member checksum mismatch: "+member.name)
    publish_new(temporary,destination)
    return destination


def tools(base):
    directory = base/'cache/tools'
    executable = directory/'venv/bin/scons'
    if executable.is_file():
        result = subprocess.run([str(executable),'--version'],capture_output=True,text=True,check=True)
        if 'SCons: v4.11.1.' not in result.stdout: raise ValueError("Unexpected cached SCons version")
        return executable
    directory.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'-m','venv',str(directory/'venv')],check=True,stdout=sys.stderr)
    # Version-pinned generic build tool, confined to this user-owned environment.
    import urllib.request
    wheel=directory/'scons-4.11.1-py3-none-any.whl'
    pin={'sha256':'454cef364348053422696e3d2ecb4fa593c96a624f955842eaaea64f95c8d11d','size_bytes':4123659}
    if not wheel.exists():
        url='https://files.pythonhosted.org/packages/8e/43/d6285848e893c19682c06e92679dc1a07d37ff7ea148747b1df681ec496c/scons-4.11.1-py3-none-any.whl'
        with urllib.request.urlopen(url,timeout=60) as response:
            raw=response.read(pin['size_bytes']+1)
        if len(raw)!=pin['size_bytes'] or hashlib.sha256(raw).hexdigest()!=pin['sha256']: raise ValueError('SCons download checksum mismatch')
        write_new(wheel,raw)
    with verified_stream(wheel,pin): pass
    subprocess.run([str(directory/'venv/bin/python'),'-m','pip','install','--disable-pip-version-check',
                    '--no-deps','--no-index',str(wheel)],check=True,stdout=sys.stderr)
    return executable


def build(root, sdk, archive):
    from pipeline import run
    from verify_output import verify
    root=job_root(root); base=root.parent.parent
    source=extract_source(root)
    sdk=Path(sdk) if sdk else root/'sdk.tar.gz'
    emit('progress',value=.40,message='Preparing private compiler tools')
    scons=tools(base)
    output=root/'native-output'
    if output.exists():
        report=verify(output,check_modes=True)
        if report['errors']: raise ValueError('Existing job output failed verification')
    else:
        stages=[('Compiling',.48),('Downloading',.66),('Transforming',.78)]
        def progress(message):
            value=next((v for prefix,v in stages if message.startswith(prefix)),.43)
            emit('progress',value=value,message=message)
        result=run(source,output,sdk=sdk,cache=base/'cache',scons=str(scons),progress=progress)
        report=verify(output,check_modes=True)
        if report['errors']: raise ValueError('Native output verification failed')
    # Persist a short, quoted, reproducible Steam entry point in every output.
    launcher=output/'play-steam.sh'
    if not launcher.exists():
        raw=b'#!/bin/sh\nROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"\nexec /usr/bin/python3 "$ROOT/steam_launch.py" "$@"\n'
        write_new(launcher,raw,0o755)
        manifest_path=output/'conversion-manifest.json'
        manifest=json.loads(manifest_path.read_bytes())
        manifest['files'].append({'path':'play-steam.sh','executable':True,'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    report=verify(output,check_modes=True)
    if report['errors']: raise ValueError('Deployment verification failed')
    archive_path=root/'output.tar'
    if archive and not archive_path.exists():
        emit('progress',value=.90,message='Packaging verified output')
        create_tar(output,archive_path)
    command='"'+str(output/'play-steam.sh')+'" %command%'
    receipt={'output':str(output),'launch_command':command,'validation':report,'archive':str(archive_path) if archive else None}
    (root/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    emit('result',**receipt)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['probe','status','upload','build','result','cleanup','steam-inspect','steam-configure','steam-restore','reuse-input'])
    parser.add_argument('root')
    parser.add_argument('--name');parser.add_argument('--size',type=int);parser.add_argument('--sha256')
    parser.add_argument('--offset',type=int,default=0);parser.add_argument('--sdk',default='');parser.add_argument('--archive',action='store_true')
    parser.add_argument('--consent',action='store_true');parser.add_argument('--isolated',action='store_true')
    args=parser.parse_args()
    try:
        if args.action.startswith('steam-'):
            import steam_entry
            root=job_root(args.name or args.root)
            if root.parent != job_root(args.root).parent: raise ValueError('Steam target must belong to the configured workspace')
            action=args.action
            result=steam_entry.inspect() if action=='steam-inspect' else (steam_entry.configure(root/'native-output',consent=args.consent,isolated=args.isolated) if action=='steam-configure' else steam_entry.restore(root/'native-output',consent=args.consent))
            emit('result',**result)
        elif args.action=='probe': probe(args.root)
        elif args.action=='status': transfer_status(args.root,args.name)
        elif args.action=='reuse-input': reuse_input(args.root,args.name,args.size,args.sha256)
        elif args.action=='upload': upload(args.root,args.name,args.size,args.sha256,args.offset)
        elif args.action=='build': build(args.root,args.sdk,args.archive)
        elif args.action=='cleanup':
            root=job_root(args.root)
            if (root/'native-output').exists(): raise ValueError('Completed game output is protected from cleanup')
            shutil.rmtree(root);emit('result',removed_failed_job=True)
        else: emit('result',**json.loads((job_root(args.root)/'result.json').read_bytes()))
    except Exception as error:
        emit('error',message=str(error));return 2
    return 0


if __name__=='__main__': sys.exit(main())
