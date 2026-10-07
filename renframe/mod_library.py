"""Machine-readable RenFrame mod-library helpers."""
from __future__ import annotations

import hashlib, json, os, re, zipfile
from pathlib import Path, PurePosixPath
from typing import Any

OPS={"copy_file","copy_tree","overlay_archive","delete","rename","mkdir","verify_exists","verify_missing"}
RUNTIME_ROOTS={"lib","renpy","update"}
NATIVE={".dll",".so",".pyd",".dylib",".exe"}
SCRIPT={".bat",".cmd",".ps1",".sh",".py"}
SHA_RE=re.compile(r"^[0-9a-f]{64}$")

class LibraryError(ValueError): pass

def repo_root()->Path:
    return Path(os.getenv("RENFRAME_REPO_ROOT") or Path(__file__).resolve().parents[1]).resolve()

def library_root(root:Path|None=None)->Path: return (root or repo_root())/"mod_library"
def slugify(s:str)->str: return re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-") or "item"

def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def _safe(p:str, allow_dot:bool=False)->str:
    p=p.replace("\\","/").strip(); q=PurePosixPath(p)
    if not p or q.is_absolute() or ".." in q.parts or (str(q)=="." and not allow_dot):
        raise LibraryError(f"unsafe relative path: {p!r}")
    return str(q)

def _load_dir(kind:str,root:Path|None=None)->list[dict[str,Any]]:
    d=library_root(root)/kind
    out=[]
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        try: r=json.loads(p.read_text("utf-8"))
        except Exception as e: raise LibraryError(f"Cannot read {p}: {e}") from e
        if not isinstance(r,dict): raise LibraryError(f"{p} is not a JSON object")
        r["_path"]=str(p); out.append(r)
    return sorted(out,key=lambda x:str(x.get("name",x.get("id",""))).lower())

def load_games(root:Path|None=None): return _load_dir("games",root)
def load_mods(root:Path|None=None): return _load_dir("mods",root)

def validate_game(r:dict[str,Any])->list[str]:
    e=[]
    if not r.get("name"): e.append("name is required")
    if not r.get("id"): e.append("id is required")
    elif slugify(str(r["id"]))!=r["id"]: e.append("id must be a lowercase slug")
    fp=r.get("fingerprint") or {}
    if not isinstance(fp,dict): e.append("fingerprint must be an object"); return e
    for p in fp.get("required_paths",[]) or []:
        try:_safe(str(p))
        except LibraryError as x:e.append(str(x))
    for x in fp.get("file_hashes",[]) or []:
        try:_safe(str(x.get("path","")))
        except Exception as z:e.append(str(z))
        if x.get("sha256") and not SHA_RE.fullmatch(str(x["sha256"])): e.append("invalid fingerprint SHA-256")
    return e

def validate_mod(r:dict[str,Any])->list[str]:
    e=[]
    if not r.get("name"): e.append("name is required")
    if not r.get("id"): e.append("id is required")
    elif slugify(str(r["id"]))!=r["id"]: e.append("id must be a lowercase slug")
    scope=r.get("scope","game")
    if scope not in {"game","universal"}: e.append("scope must be game or universal")
    if scope=="game" and not r.get("game_id"): e.append("game_id is required")
    art=r.get("artifact") or {}; digest=art.get("sha256") if isinstance(art,dict) else None
    if digest and not SHA_RE.fullmatch(str(digest)): e.append("artifact SHA-256 is invalid")
    install=r.get("install") or []
    if not isinstance(install,list): return e+["install must be a list"]
    for n,op in enumerate(install,1):
        if not isinstance(op,dict) or op.get("op") not in OPS: e.append(f"operation {n} is invalid"); continue
        for k in ("source","destination","path"):
            if k in op:
                try:_safe(str(op[k]),True)
                except LibraryError as x:e.append(f"operation {n}: {x}")
    return e

def validate_library(root:Path|None=None)->list[str]:
    games,mods=load_games(root),load_mods(root); ids={g.get("id") for g in games}; e=[]
    for g in games:e += [f"game {g.get('id','?')}: {x}" for x in validate_game(g)]
    for m in mods:
        e += [f"mod {m.get('id','?')}: {x}" for x in validate_mod(m)]
        if m.get("scope","game")=="game" and m.get("game_id") not in ids:e.append(f"mod {m.get('id')}: unknown game_id {m.get('game_id')}")
    if len(ids)!=len(games):e.append("duplicate game id")
    mids=[m.get("id") for m in mods]
    if len(set(mids))!=len(mids):e.append("duplicate mod id")
    return e

def _write(kind:str,r:dict[str,Any],root:Path|None=None)->Path:
    errs=validate_game(r) if kind=="games" else validate_mod(r)
    if errs:raise LibraryError("; ".join(errs))
    d=library_root(root)/kind; d.mkdir(parents=True,exist_ok=True); p=d/f"{r['id']}.json"
    p.write_text(json.dumps({k:v for k,v in r.items() if not k.startswith('_')},indent=2,ensure_ascii=False)+"\n","utf-8")
    return p

def save_game(r,root=None): return _write("games",r,root)
def save_mod(r,root=None): return _write("mods",r,root)
def delete_record(r):
    if r.get("_path"): Path(r["_path"]).unlink(missing_ok=True)

def write_index(root:Path|None=None)->Path:
    games,mods=load_games(root),load_mods(root)
    data={"schema_version":1,"games":[{"id":g["id"],"name":g["name"]} for g in games],"mods":[{"id":m["id"],"name":m["name"],"game_id":m.get("game_id"),"scope":m.get("scope","game"),"adult":bool(m.get("adult"))} for m in mods]}
    p=library_root(root)/"catalog.json"; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n","utf-8"); return p

def inspect_package(path:Path|str)->dict[str,Any]:
    p=Path(path).expanduser().resolve()
    if not p.exists(): raise LibraryError(f"package not found: {p}")
    digest=None
    if p.is_dir(): entries=[str(x.relative_to(p)).replace(os.sep,"/") for x in p.rglob("*") if x.is_file()]; kind="directory"
    elif zipfile.is_zipfile(p):
        digest=sha256_file(p); kind="zip"
        with zipfile.ZipFile(p) as z: entries=[i.filename for i in z.infolist() if not i.is_dir()]
    elif p.suffix.lower() in {".rar",".7z"}:
        raise LibraryError(f"{p.suffix} archives are not inspected yet; extract the archive and select the folder instead")
    else: entries=[p.name]; digest=sha256_file(p); kind=p.suffix.lower().lstrip(".") or "file"
    unsafe=[]; top=set(); runtime=False; executables=[]
    for raw in entries:
        s=raw.replace("\\","/")
        while s.startswith("./"):s=s[2:]
        try:q=PurePosixPath(_safe(s))
        except LibraryError:unsafe.append(raw);continue
        if q.parts: top.add(q.parts[0])
        if q.suffix.lower() in NATIVE|SCRIPT:executables.append(str(q))
        if (q.parts and q.parts[0].lower() in RUNTIME_ROOTS) or q.suffix.lower() in NATIVE:runtime=True
    files=[x.replace("\\","/") for x in entries if x and not x.endswith("/")]
    meaningful=[x for x in files if PurePosixPath(x).name.lower() not in {"readme","readme.txt","readme.md","license","license.txt","license.md"}]
    rpa=[x for x in meaningful if "/" not in x and x.lower().endswith(".rpa")]
    lower={x.lower() for x in top}
    if len(rpa)==1 and len(meaningful)==1:
        n=PurePosixPath(rpa[0]).name; method="copy_rpa_to_game"; ops=[{"op":"copy_file","source":n,"destination":f"game/{n}"}]
    elif lower&RUNTIME_ROOTS: method="overlay_game_root"; ops=[{"op":"overlay_archive","source":".","destination":"."}]
    elif "game" in lower: method="merge_game_directory"; ops=[{"op":"copy_tree","source":"game","destination":"game","merge":True}]
    elif executables: method="custom"; ops=[]
    elif runtime: method="overlay_game_root"; ops=[{"op":"overlay_archive","source":".","destination":"."}]
    else: method="contents_to_game"; ops=[{"op":"overlay_archive","source":".","destination":"game"}]
    return {"path":str(p),"kind":kind,"sha256":digest,"file_count":len(entries),"top_level":sorted(top),"unsafe_entries":sorted(unsafe),"executable_entries":sorted(executables),"runtime_sensitive":runtime,"suggested_method":method,"suggested_operations":ops}

def fingerprint_game(path:Path|str)->dict[str,Any]:
    from renframe.inspect_service import inspect_game
    root=Path(path).resolve(); info=inspect_game(root)
    if not info.is_renpy:raise LibraryError("not recognized as a Ren'Py game")
    candidates=[]
    for name in ("scripts.rpa","archive.rpa"):
        q=root/"game"/name
        if q.is_file():candidates.append(q)
    if (root/"game").is_dir():
        for q in sorted((root/"game").glob("*.rpa")):
            if q not in candidates:candidates.append(q)
            if len(candidates)>=3:break
    hashes=[{"path":str(q.relative_to(root)).replace(os.sep,"/"),"sha256":sha256_file(q),"size":q.stat().st_size} for q in candidates[:3]]
    launchers=sorted([q.name for pat in ("*.sh","*.exe") for q in root.glob(pat) if q.is_file()])
    return {"name":info.game_name,"renpy_version":info.renpy_version,"fingerprint":{"launcher_names":launchers,"required_paths":[x["path"] for x in hashes],"file_hashes":hashes,"confidence":"seed"}}
