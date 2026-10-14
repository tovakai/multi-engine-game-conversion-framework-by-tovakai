"""Isolated Until Then research build. Never reads/writes Steam game directories."""
from pathlib import Path
import hashlib,json,subprocess,sys,urllib.request,platform
BASE=Path.home()/'.cache/megcfbt/research/until-then'
BASE.mkdir(parents=True,exist_ok=True)
assert platform.machine()=='aarch64'
def run(*args,cwd=None):
 print('BUILD', ' '.join(str(x) for x in args),flush=True)
 subprocess.run([str(x) for x in args],cwd=cwd,check=True)
def clone(name,repo,tag,expected):
 dest=BASE/name
 if not dest.exists():run('git','clone','--depth','1','--branch',tag,repo,dest)
 actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dest,text=True).strip()
 if actual!=expected:raise ValueError('Unexpected existing source checkout: '+name)
 return dest
venv=BASE/'build-venv'
if not venv.exists():run('python3','-m','venv',venv)
python=venv/'bin/python'
run(python,'-m','pip','install','scons==4.9.1')
native=BASE/'native';native.mkdir(exist_ok=True)
cpp=clone('godot-cpp','https://github.com/godotengine/godot-cpp.git','godot-4.1.4-stable','4b0ee133274d67687b6003b8d5fdaf7b79cf4921')
link=native/'godot-cpp'
if not link.exists():link.symlink_to(cpp,target_is_directory=True)
if link.resolve()!=cpp.resolve():raise ValueError('Unexpected build dependency link')
header=native/'third-party/nlohmann/json.hpp';header.parent.mkdir(parents=True,exist_ok=True)
if not header.exists():urllib.request.urlretrieve('https://raw.githubusercontent.com/nlohmann/json/v3.10.4/single_include/nlohmann/json.hpp',header)
manifest={'godot_cpp':'4b0ee133274d67687b6003b8d5fdaf7b79cf4921','nlohmann_json_version':'3.10.4','nlohmann_header_sha256':hashlib.sha256(header.read_bytes()).hexdigest()}
(BASE/'build-inputs.json').write_text(json.dumps(manifest,indent=2))
run(python,'-m','SCons','platform=linux','arch=arm64','target=template_release','-j3',cwd=native)
print('NATIVE_REPLACEMENTS_BUILT',flush=True)
