"""Compare experimental helpers with the user's original DLLs in an isolated project.

No game pack, saves, Steam settings or original files are modified/copied into Git.
"""
from pathlib import Path
import argparse,hashlib,json,random,shutil,subprocess,uuid
ROOT=Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(source: Path, workspace: Path):
    source=source.resolve(strict=True)
    workspace=workspace.resolve()
    if workspace==source or source in workspace.parents or workspace in source.parents:
        raise ValueError('Oracle workspace must be separate from source installation')
    profile=json.loads((ROOT/'source-profile.json').read_text())
    for name,expected in profile['oracle_dll_sha256'].items():
        path=source/name
        if path.is_symlink() or not path.is_file() or digest(path)!=expected:
            raise ValueError('Oracle library does not match audited research input: '+name)
    workspace.mkdir(parents=True,exist_ok=True)
    project=workspace/('oracle-'+uuid.uuid4().hex[:12]);project.mkdir()
    for name in ['UntilThen.exe','internal.dll','jsonutils.dll']:
        shutil.copyfile(source/name,project/name)
    for path in (ROOT/'prototypes').glob('*.gd'):
        shutil.copyfile(path,project/path.name)
    for path in (ROOT/'tests').glob('*.gd'):
        shutil.copyfile(path,project/path.name)
    (project/'project.godot').write_text('[application]\nconfig/name="MEGCFBT Until Then isolated oracle"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
    (project/'.godot').mkdir();(project/'.godot/global_script_class_cache.cfg').write_text('list=[]\n')
    for name in ['internal','jsonutils']:
        (project/(name+'.gdextension')).write_text('[configuration]\nentry_symbol="'+name+'_library_init"\ncompatibility_minimum=4.1\n[libraries]\nwindows.release="res://'+name+'.dll"\nwindows.debug="res://'+name+'.dll"\n')
    rng=random.Random(1574820)
    def value(depth=0):
        if depth>2:return rng.choice([None,True,False,0,1,2.5,'text','/~'])
        kind=rng.randrange(5)
        if kind==0:return {key:value(depth+1) for key in rng.sample(['a','b','c','a/b','~x',''],rng.randrange(5))}
        if kind==1:return [value(depth+1) for _ in range(rng.randrange(5))]
        return value(3)
    cases=json.loads((ROOT/'tests/json_fixtures.json').read_text())
    for _ in range(250):
        a,b=value(),value()
        cases.append({'before':a if isinstance(a,dict) else {'root':a},'after':b if isinstance(b,dict) else {'root':b}})
    (project/'inputs.json').write_text(json.dumps(cases),encoding='utf-8')
    receipts=[]
    for script,report in [('json_parity.gd','json-parity.json'),('camera_parity.gd','camera-parity.json'),('color_parity.gd','color-parity.json')]:
        result=subprocess.run([str(project/'UntilThen.exe'),'--headless','--path',str(project),'--script','res://'+script],capture_output=True,timeout=30)
        (project/(script+'.log')).write_bytes(result.stdout+result.stderr)
        if result.returncode!=0:raise RuntimeError(f'{script} failed ({result.returncode}); inspect {project}')
        details=json.loads((project/report).read_text())
        if details['failures']:raise RuntimeError(f'{script}: behavior mismatch')
        receipts.append({'test':script,'result':details})
        print(script,details['cases'],'passed',flush=True)
    output={'status':'prototype-oracle-passed','gameplay':'not tested','oracle_profile':profile,'engine_sha256':digest(source/'UntilThen.exe'),'prototypes':{p.name:digest(p) for p in (ROOT/'prototypes').glob('*.gd')},'results':receipts}
    (workspace/'oracle-summary.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(workspace/'oracle-summary.json')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--workspace',type=Path,default=ROOT.parents[1]/'build/until-then-oracle')
    args=parser.parse_args();run(args.source,args.workspace)
