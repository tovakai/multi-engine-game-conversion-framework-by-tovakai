"""Build matching Godot 4.1.4 in the isolated research cache, not a Steam library."""
from pathlib import Path
import subprocess,platform
assert platform.machine()=='aarch64'
base=Path.home()/'.cache/megcfbt/research/until-then';source=base/'godot-4.1.4';python=base/'build-venv/bin/python'
if not source.exists():subprocess.run(['git','clone','--depth','1','--branch','4.1.4-stable','https://github.com/godotengine/godot.git',str(source)],check=True)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()=='fe0e8e55752b0c2e64997025717b491703e0f8ad'
# GCC 15 no longer supplies transitive fixed-width integer declarations.
header=source/'thirdparty/glslang/SPIRV/SpvBuilder.h'
text=header.read_text()
if '#include <cstdint>' not in text:
 header.write_text('#include <cstdint>\n'+text)
header=source/'thirdparty/thorvg/inc/thorvg.h'
text=header.read_text()
if '#include <cstdint>' not in text:header.write_text('#include <cstdint>\n'+text)
# GCC 15 validates unused template debug printers; their old field names are invalid.
for relative,old,new in [
 ('thirdparty/embree/kernels/subdiv/bezier_curve.h','"QuadraticBezierCurve ( (" << a.u.lower << ", " << a.u.upper << "), "','"QuadraticBezierCurve ( "'),
 ('thirdparty/embree/kernels/geometry/pointi.h','"i {" << line.v0 << ", " << line.geomID()','"i {" << line.geomID()')]:
 path=source/relative
 text=path.read_text()
 if old in text:
  assert text.count(old)==1
  path.write_text(text.replace(old,new))
subprocess.run([str(python),'-m','SCons','platform=linuxbsd','target=template_release','arch=arm64','-j2'],cwd=source,check=True)
print('GODOT_RUNTIME_BUILT',flush=True)
