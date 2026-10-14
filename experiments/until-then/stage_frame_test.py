from pathlib import Path
import hashlib,json,shutil,tarfile,os,struct,subprocess
base=Path.home()/'.cache/megcfbt/research/until-then'
root=Path('/run/media/steamos/SD512/megcfbt-research/until-then-20261014')
assert root.resolve()==root and 'steamapps' not in root.parts
with tarfile.open(base/'until-then-support.tar.gz') as package:package.extractall(root,filter='data')
profile=json.loads((root/'source-profile.json').read_text())
pack=root/'game/UntilThen.pck'
upload=root/'game/UntilThen.pck.uploading'
path=upload if upload.exists() else pack
assert path.is_file() and not path.is_symlink() and path.stat().st_nlink==1
h=hashlib.sha256()
with path.open('rb') as f:
 while chunk:=f.read(8*1024*1024):h.update(chunk)
assert h.hexdigest()==profile['source_pack_sha256'] and path.stat().st_size==profile['source_pack_size']
if path==upload:
 assert not pack.exists()
 upload.rename(pack)

def copy(source,target,executable=False):
 target=root/target
 for parent in target.parents:
  if parent==root.parent:break
  assert not parent.is_symlink()
 target.parent.mkdir(parents=True,exist_ok=True)
 assert not target.is_symlink()
 if target.exists():assert target.is_file() and target.stat().st_nlink==1
 shutil.copyfile(source,target)
 if executable:target.chmod(0o755)
 return target
runtime=copy(base/'godot-4.1.4/bin/godot.linuxbsd.template_release.arm64','runtime/godot.arm64',True)
lib=base/'native/bin/libuntilthen.linux.template_release.arm64.so'
libs=[copy(lib,'game/addons/internal/linux/libinternal.so'),copy(lib,'game/addons/jsonutils/linux/libjsonutils.so')]
libs.append(copy(base/'inkcpp/bin/libinkcpp.megcfbt.arm64.so','game/addons/inkcpp/linux/libinkcpp.so'))
libs.append(copy(base/'threen/bin/libthreen.megcfbt.arm64.so','game/addons/threen/linux/libthreen.so'))
libs.append(copy(base/'steam-4.1/bin/libgodotsteam.megcfbt.arm64.so','game/addons/godotsteam/linux/libgodotsteam.so'))
libs.append(copy(base/'steam-4.1/godotsteam/sdk/native/libsteam_api.so','game/addons/godotsteam/linux/libsteam_api.so'))
libs.append(copy(base/'fmod-for-godot/addons/FMOD/native/bin/libfmod.megcfbt.arm64.so','game/addons/fmod/native/linux/libfmod.release.so'))
sdk=base/'sdk/fmodstudioapi20235linux'
for module in ['core','studio']:
 for source in (sdk/f'api/{module}/lib/arm64').glob('libfmod*.so*'):
  if 'libfmodL' in source.name or 'libfmodstudioL' in source.name:continue
  assert source.resolve().is_relative_to(sdk.resolve())
  libs.append(copy(source,'game/addons/fmod/native/linux/'+source.name))
for path in libs+[runtime]:
 with path.open('rb') as f:header=f.read(64)
 assert header[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',header,18)[0]==183
for name in ['launch.sh','install-to-steam.sh']:(root/name).chmod(0o755)
copy(root/'override.cfg','game/override.cfg')
(root/'native-test-build.json').write_text(json.dumps({'status':'startup-not-yet-tested','source_pack_sha256':h.hexdigest(),'libraries':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in libs},'runtime_sha256':hashlib.sha256(runtime.read_bytes()).hexdigest()},indent=2))
env=os.environ.copy();env['LD_LIBRARY_PATH']=str(root/'game/addons/fmod/native/linux')+':'+str(root/'game/addons/godotsteam/linux')
result=subprocess.run(['ldd','-r',str(root/'game/addons/fmod/native/linux/libfmod.release.so')],capture_output=True,text=True,env=env)
print(result.stdout,result.stderr,flush=True)
print('NATIVE_TEST_PACKAGE_READY',root,flush=True)
