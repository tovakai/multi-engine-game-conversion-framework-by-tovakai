"""Build pinned public InkCPP, Threen and genuine Steam bindings in research cache."""
from pathlib import Path
import subprocess,shutil,sys
base=Path.home()/'.cache/megcfbt/research/until-then';cpp=base/'godot-cpp';python=base/'build-venv/bin/python'
def run(*args,cwd=None):subprocess.run([str(x) for x in args],cwd=cwd,check=True)
def checkout(directory,url,commit):
 if not directory.exists():
  directory.mkdir()
  run('git','init',directory)
  run('git','remote','add','origin',url,cwd=directory)
  run('git','fetch','--depth','1','origin',commit,cwd=directory)
  run('git','checkout','--detach','FETCH_HEAD',cwd=directory)
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=directory,text=True).strip()==commit
 return directory

def recipe(directory,sources,includes=(),defines=(),libraries=(),libpaths=(),name='extension'):
 text="env=Environment(CXX='g++',CCFLAGS=['-fPIC','-std=c++17','-O2','-fno-gnu-unique','-fvisibility=hidden'],CPPDEFINES="+repr(['NDEBUG']+list(defines))+",CPPPATH="+repr([str(cpp/'include'),str(cpp/'gen/include'),str(cpp/'gdextension')]+list(includes))+",LIBPATH="+repr([str(cpp/'bin')]+list(libpaths))+",LIBS="+repr(['godot-cpp.linux.template_release.arm64']+list(libraries))+",LINKFLAGS=[\"-Wl,-rpath,'$$ORIGIN'\",\"-Wl,-Bsymbolic\",\"-Wl,--exclude-libs,ALL\"])\nDefault(env.SharedLibrary('bin/lib"+name+".megcfbt.arm64.so',"+repr(sources)+"))\n"
 (directory/'SConstruct.megcfbt').write_text(text)
 run(python,'-m','SCons','-f','SConstruct.megcfbt','-j2',cwd=directory)

component=sys.argv[1]
if component=='inkcpp':
 directory=checkout(base/'inkcpp','https://github.com/semickolon/godot-inkcpp.git','fe1b761f47ecd1c04d2dc366d3d817957f4eb608')
 entry=directory/'src/register_types.cpp';text=entry.read_text();text=text.replace('const GDExtensionInterface *p_interface','GDExtensionInterfaceGetProcAddress p_interface');entry.write_text(text)
 header=directory/'inkcpp/random.h'
 text=header.read_text()
 if '#include <cstdint>' not in text:header.write_text('#include <cstdint>\n'+text)
 header=directory/'shared/private/header.h'
 text=header.read_text()
 if '#include <cstdint>' not in text:header.write_text('#include <cstdint>\n'+text)
 files=[str(p.relative_to(directory)) for path in ['src','inkcpp'] for p in (directory/path).glob('*.cpp')]
 recipe(directory,files,['src','inkcpp/include','shared/private','shared/public'],['INK_ENABLE_GODOT'],name='inkcpp')
elif component=='threen':
 directory=checkout(base/'threen','https://github.com/akien-mga/threen.git','4ee5588cb8ee203048ab66c89377e29e78ab82a3')
 entry=directory/'src/register_types.cpp';text=entry.read_text()
 marker='// MEGCFBT: explicit UI bindings for old lazy engine-class registration'
 if marker not in text:
  text=text.replace('#include "threen.h"','#include "threen.h"\n#include <godot_cpp/classes/control.hpp>\n#include <godot_cpp/classes/v_box_container.hpp>')
  text=text.replace('ClassDB::register_class<Threen>();',marker+'\n godot::internal::EngineClassRegistration<godot::Control>::callback();\n godot::internal::EngineClassRegistration<godot::VBoxContainer>::callback();\n ClassDB::register_class<Threen>();')
  entry.write_text(text)
 files=[str(p.relative_to(directory)) for p in (directory/'src').glob('*.cpp')]
 if not files:files=[str(p.relative_to(directory)) for p in directory.glob('*.cpp')]
 recipe(directory,files,['src','.'],name='threen')
elif component=='steam':
 directory=checkout(base/'steam-4.1','https://codeberg.org/godotsteam/godotsteam.git','84ece1a226b8fd099333940e7a3b8367efb59370')
 proton=checkout(base/'proton-sdk','https://github.com/ValveSoftware/Proton.git','5b89db940e0ebe3a137a6009a3589232fe084c09')
 headers=directory/'godotsteam/sdk/public_158/steam'
 if not headers.exists():
  shutil.copytree(proton/'lsteamclient/steamworks_sdk_158',headers)
  sys.path.insert(0,str(base))
  from steam_sdk_compat import NETWORKING_INLINE_HELPERS
  for filename,old,new in [('isteamremoteplay.h','} data;','};'),('isteaminput.h','} x;','};'),('steamnetworkingtypes.h','} data;','};')]:
   path=headers/filename
   text=path.read_text()
   if old in text:path.write_text(text.replace(old,new))
  path=headers/'steamnetworkingtypes.h'
  text=path.read_text().replace('#if 0\ninline void SteamNetworkingIPAddr::Clear()','#if 1\ninline void SteamNetworkingIPAddr::Clear()')
  path.write_text(text)
  path=headers/'steam_api.h'
  path.write_text(path.read_text()+'\n'+NETWORKING_INLINE_HELPERS)
 runtime=directory/'godotsteam/sdk/native';runtime.mkdir(exist_ok=True)
 source=Path('/opt/steamvr/bin/linuxarm64/libsteam_api.so')
 if not source.is_file():raise ValueError('Genuine installed AArch64 Steam API unavailable')
 shutil.copyfile(source,runtime/'libsteam_api.so')
 files=[str(p.relative_to(directory)) for p in (directory/'godotsteam').glob('*.cpp')]
 recipe(directory,files,['godotsteam','godotsteam/sdk/public_158'],libraries=['steam_api'],libpaths=[str(runtime)],name='godotsteam')
else:raise ValueError('Unknown research component')
print('PUBLIC_EXTENSION_BUILT',component,flush=True)
