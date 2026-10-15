from pathlib import Path
import shutil,tarfile,subprocess,json
base=Path.home()/'.cache/megcfbt/research/until-then';project=base/'linux-prototype-tests';project.mkdir(exist_ok=True)
with tarfile.open(base/'linux-prototype-tests.tar.gz') as package:package.extractall(project,filter='data')
(project/'project.godot').write_text('[application]\nconfig/name="Until Then Linux isolated prototype tests"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
(project/'.godot').mkdir(exist_ok=True);(project/'.godot/global_script_class_cache.cfg').write_text('list=[]\n')
for name in ['internal','jsonutils']:
 shutil.copyfile(base/'native/bin/libuntilthen.linux.template_release.arm64.so',project/(name+'.so'))
 (project/(name+'.gdextension')).write_text('[configuration]\nentry_symbol="'+name+'_library_init"\ncompatibility_minimum=4.1\n[libraries]\nlinux.release="res://'+name+'.so"\nlinux.debug="res://'+name+'.so"\n')
engine=base/'godot-4.1.4/bin/godot.linuxbsd.template_release.arm64'
for script,report in [('json_parity.gd','json-parity.json'),('camera_parity.gd','camera-parity.json'),('color_parity.gd','color-parity.json')]:
 result=subprocess.run([str(engine),'--headless','--path',str(project),'--script','res://'+script],capture_output=True,timeout=30)
 (project/(script+'.log')).write_bytes(result.stdout+result.stderr)
 print(script,result.returncode,(result.stdout+result.stderr).decode(errors='replace')[-500:],flush=True)
 if result.returncode:raise RuntimeError('Native test failed; see isolated logs')
 assert not json.loads((project/report).read_text())['failures']
print('NATIVE_LINUX_PROTOTYPES_VERIFIED',flush=True)
