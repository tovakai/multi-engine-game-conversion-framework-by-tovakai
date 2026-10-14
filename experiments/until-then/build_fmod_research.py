"""Build the preserved FMOD integration fork against owner-supplied SDK; research only."""
from pathlib import Path
import subprocess,tarfile,hashlib,json
base=Path.home()/'.cache/megcfbt/research/until-then'
archive=base/'fmodstudioapi20235linux.tar.gz'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='855381248a85b6457b96090c9f9c0b070a51f10be6bf07b4a6456a12f8aff807'
sdk=base/'sdk'
if not (sdk/'fmodstudioapi20235linux').exists():
 sdk.mkdir(exist_ok=True)
 with tarfile.open(archive) as pack:pack.extractall(sdk,filter='data')
sdk=sdk/'fmodstudioapi20235linux'
source=base/'fmod-for-godot'
if not source.exists():subprocess.run(['git','clone','--depth','1','https://github.com/MadFlyFish/fmod-for-godot.git',str(source)],check=True)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()=='2046fb9ef051c4e3936f363d01ba5784052a787f'
native=source/'addons/FMOD/native'
entry=native/'src/register_types.cpp'
text=entry.read_text();old='const GDExtensionInterface* p_interface';new='GDExtensionInterfaceGetProcAddress p_interface'
if old in text:
 assert text.count(old)==1
 (native/'register_types.cpp.before-4.1').write_text(text)
 text=text.replace(old,new).replace('init_obj.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_EDITOR)','init_obj.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE)')
 entry.write_text(text)
assert new in text
# Modern bindings require enum visibility and explicit standard includes.
header=native/'src/fmod_studio_editor_module.h'
text=header.read_text()
text=text.replace('enum FMODAssetType', 'public:\n\tenum FMODAssetType',1) if 'public:\n\tenum FMODAssetType' not in text else text
text=text.replace('enum FMODIconType', 'public:\n\tenum FMODIconType',1) if 'public:\n\tenum FMODIconType' not in text else text
header.write_text(text)
header=native/'src/fmod_assets.h'
text=header.read_text()
if '#include <utility>' not in text:header.write_text('#include <utility>\n'+text)
# Stop real FMOD workers before Godot unloads their callbacks/library.
header=native/'src/fmod_studio_module.h'
text=header.read_text().replace('FMOD::Studio::System* studio_system;', 'FMOD::Studio::System* studio_system = nullptr;')
header.write_text(text)
module=native/'src/fmod_studio_module.cpp'
text=module.read_text().replace('if (studio_system->isValid())','if (studio_system != nullptr && studio_system->isValid())')
old='if (ERROR_CHECK(studio_system->release()))\n\t\t{\n\t\t\treturn true;'
new='if (ERROR_CHECK(studio_system->release()))\n\t\t{\n\t\t\tstudio_system = nullptr;\n\t\t\treturn true;'
if old in text:text=text.replace(old,new)
assert 'studio_system = nullptr;' in text
module.write_text(text)
entry=native/'src/register_types.cpp'
text=entry.read_text()
old='Engine::get_singleton()->unregister_singleton("FMODStudioModule");'
new='if (fmod_module != nullptr) { fmod_module->shutdown(); }\n\t\t'+old
if 'fmod_module->shutdown();' not in text:text=text.replace(old,new)
assert 'fmod_module->shutdown();' in text
entry.write_text(text)
recipe=native/'SConstruct.megcfbt'
recipe.write_text('''from pathlib import Path
root=Path.home()/'.cache/megcfbt/research/until-then'
cpp=root/'godot-cpp'
sdk=root/'sdk/fmodstudioapi20235linux'
env=Environment(CXX='g++',CCFLAGS=['-fPIC','-std=c++17','-O2','-fno-gnu-unique','-fvisibility=hidden'],CPPDEFINES=['FMOD_LINUX','NDEBUG'],
 CPPPATH=[str(cpp/'include'),str(cpp/'gen/include'),str(cpp/'gdextension'),'src',str(sdk/'api/core/inc'),str(sdk/'api/studio/inc')],
 LIBPATH=[str(cpp/'bin'),str(sdk/'api/core/lib/arm64'),str(sdk/'api/studio/lib/arm64')],
 LIBS=['godot-cpp.linux.template_release.arm64','fmod','fmodstudio'],LINKFLAGS=["-Wl,-rpath,'$$ORIGIN'","-Wl,-Bsymbolic","-Wl,--exclude-libs,ALL"])
sources=[str(path) for path in Path('src').rglob('*.cpp')]
Default(env.SharedLibrary('bin/libfmod.megcfbt.arm64.so',sources))
''')
subprocess.run([str(base/'build-venv/bin/python'),'-m','SCons','-f',recipe.name,'-j2'],cwd=native,check=True)
print('FMOD_NATIVE_BUILT',flush=True)
