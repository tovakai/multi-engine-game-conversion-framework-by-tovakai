"""Train45 production routing, embedded v3 PCK extraction and ZIP contract."""
import hashlib
import json
import struct
import zipfile
from pathlib import Path
import pytest
from megcfbt import router, steam_library
from rpgmframe import train45 as profile, godot_extension_runtime as runtime
from tests.test_until_then_conversion import elf, tar_files, snapshot


@pytest.fixture
def train(tmp_path, monkeypatch):
    source = tmp_path / "Steam/steamapps/common/Train45"
    source.mkdir(parents=True)
    data = b"Independent synthetic game content"
    name = b"project.binary" + bytes(2)
    directory = struct.pack("<I", 1) + struct.pack("<I", len(name)) + name + struct.pack("<QQ", 0, len(data)) + hashlib.md5(data).digest() + struct.pack("<I", 0)
    body = struct.pack("<6IQQ", 0x43504447, 3, 4, 5, 0, 2, 112, 112 + len(data)) + bytes(72) + data + directory
    (source / "Train45.exe").write_bytes(b"MZ" + bytes(126) + body + struct.pack("<QI", len(body), 0x43504447))
    hashes = {}
    for name in profile.SOURCE_LIBRARIES:
        b = ("Synthetic Windows library " + name).encode()
        (source / name).write_bytes(b);hashes[name] = hashlib.sha256(b).hexdigest()
    (source / "notes.txt").write_text("Retained companion")
    monkeypatch.setattr(profile, "SOURCE_LIBRARIES", hashes)
    monkeypatch.setattr(profile, "PACK_SIZE", len(body))
    monkeypatch.setattr(profile, "PACK_SHA256", hashlib.sha256(body).hexdigest())
    bundle = tmp_path / "runtime";bundle.mkdir()
    payload = {n:elf() for n in runtime.TRAIN_REQUIRED}
    payload["licenses/LICENSE-Godot.txt"] = b"Synthetic MIT license"
    pinned = {n:hashlib.sha256(b).hexdigest() for n,b in payload.items()}
    payload["runtime.json"] = json.dumps({"recipe_id": profile.RECIPE,"engine_version":"4.5.0","architecture":"aarch64",
        "capabilities":{"steam_api_provider":"steam-frame-installed","build_mode":"release"},"files":pinned}).encode()
    for name,b in payload.items():
        p=bundle/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    archive=tmp_path/(profile.RECIPE+".tar.gz");tar_files(archive,payload)
    entry={"recipe_id":profile.RECIPE,"executable":"godot.arm64","archive_name":archive.name,"archive_files":sorted(payload),"files":pinned,
        "sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),"url":"https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/runtime-train45-arm64-v1/"+archive.name}
    index=tmp_path/"runtime-index.json";index.write_text(json.dumps({"recipes":{profile.RECIPE:entry}}));monkeypatch.setattr(runtime,"INDEX_PATH",index)
    monkeypatch.setattr(router,"complete_frame_artwork",lambda *a,**kw:None)
    return source,bundle,archive,body


def convert(tmp_path,train,**kwargs):
    return router.build_source(train[0],output=tmp_path/"converted",backend_runtime=train[1],archive=True,**kwargs)


@pytest.mark.parametrize("manifest",[False,True])
def test_production_pipeline_and_both_zip_metadata_copies(tmp_path,train,manifest):
    source,bundle,_,body=train
    if manifest:(source.parents[1]/"appmanifest_3711590.acf").write_text('"AppState" {"appid" "3711590" "installdir" "Train45"}')
    before=snapshot(source);runtime_before=snapshot(bundle)
    inspection=router.inspect_source(source)
    assert inspection.buildable and inspection.runtime_kind==profile.RUNTIME_KIND
    result=convert(tmp_path,train)
    assert (result.output_path/"game/Train45.pck").read_bytes()==body
    assert (result.output_path/"game/notes.txt").read_text()=="Retained companion"
    assert not list(result.output_path.rglob("*.dll"))
    assert not (result.output_path/"game/addons/godotsteam/linuxarm64/libsteam_api.so").exists()
    assert "megcfbt/train45" in (result.output_path/"game/override.cfg").read_text()
    assert snapshot(source)==before and snapshot(bundle)==runtime_before
    with zipfile.ZipFile(result.archive_path) as z:
        metas=[n for n in z.namelist() if n.endswith('/.megcfbt/package.json')];assert len(metas)==2
        for n in metas:
            m=json.loads(z.read(n));assert m["backend"]=="rpgmframe" and m["engine"]=="godot"
            assert m["compatibility_profile"]==profile.PROFILE and m["runtime_engine_version"]=="4.5.0"
            assert m["steam_runtime_appid"]==3711590 and steam_library.identity(m)==3711590
            assert steam_library.capability(m)[0] is False
        launcher=z.read(next(n for n in z.namelist() if n.endswith('/payload/launch.sh')))
        assert b'export SteamAppId=3711590\nexport SteamGameId=3711590\n' in launcher
        assert b'ln -s' in launcher and b'Unexpected native Steam API path' in launcher and b'\r' not in launcher
        assert b'proton' not in launcher.lower() and b'fex' not in launcher.lower()


def test_modified_pack_fails_without_replacing_previous_output(tmp_path,train):
    convert(tmp_path,train);before=snapshot(tmp_path/"converted")
    path=train[0]/"Train45.exe";b=bytearray(path.read_bytes());b[250]^=1;path.write_bytes(b)
    with pytest.raises(router.ConversionError,match="audited build"):convert(tmp_path,train,force=True)
    assert snapshot(tmp_path/"converted")==before


def test_conflicting_manifest_fails_safely(tmp_path,train):
    source=train[0];(source.parents[1]/"appmanifest_123.acf").write_text('"AppState" {"appid" "123" "installdir" "Train45"}')
    with pytest.raises(router.ConversionError,match="[Cc]onflict"):convert(tmp_path,train)
    assert not (tmp_path/"converted").exists()


def test_embedded_bundle_needs_no_network(tmp_path,train,monkeypatch):
    import urllib.request
    monkeypatch.setattr(runtime,"EMBEDDED_PATH",train[2].parent);monkeypatch.setattr(runtime,"_cache_parent",lambda:tmp_path/"cache")
    monkeypatch.setattr(urllib.request,"urlopen",lambda *a,**kw:pytest.fail("Unexpected network"))
    selected=runtime.resolve_runtime(recipe=profile.RECIPE)
    assert runtime.validate_runtime(selected,recipe=profile.RECIPE)


@pytest.mark.parametrize("mutation",["wrong-engine","debug-mode","modified-runtime"])
def test_invalid_runtime_fails_closed(tmp_path,train,mutation):
    path=train[1]/"runtime.json";m=json.loads(path.read_text())
    if mutation=="wrong-engine":m["engine_version"]="4.6.0"
    elif mutation=="debug-mode":m["capabilities"]["build_mode"]="debug"
    else:(train[1]/"godot.arm64").write_bytes(b"MZ wrong architecture")
    path.write_text(json.dumps(m))
    with pytest.raises(router.ConversionError):convert(tmp_path,train)
    assert not (tmp_path/"converted").exists()


def test_duplicate_force_conversion_is_idempotent(tmp_path,train):
    first=convert(tmp_path,train);second=convert(tmp_path,train,force=True)
    assert first.archive_path==second.archive_path
    assert (second.output_path/"game/Train45.pck").read_bytes()==train[3]


def test_symlink_source_is_rejected(tmp_path,train):
    path=train[0]/"unsafe.txt"
    try:path.symlink_to(train[1]/"godot.arm64")
    except OSError:pytest.skip("Symlink privileges unavailable")
    with pytest.raises(router.ConversionError):convert(tmp_path,train)


def test_embedded_asset_module_names_do_not_identify_engine_modules(tmp_path,train):
    from rpgmframe.godot import find_godot_pack,inspect_godot_executable
    path=train[0]/"Train45.exe"
    data=bytearray(path.read_bytes());marker=b"get_godotsteam_version"
    data[240:240+len(marker)]=marker;path.write_bytes(data)
    assert inspect_godot_executable(train[0],find_godot_pack(train[0])) is None


def test_changed_extension_remains_unsupported(tmp_path,train):
    (train[0]/next(iter(profile.SOURCE_LIBRARIES))).write_bytes(b"Unsupported extension update")
    inspection=router.inspect_source(train[0])
    assert inspection.runtime_kind != profile.RUNTIME_KIND


def test_forged_appid_sidecar_does_not_override_verified_profile(tmp_path,train):
    (train[0]/"steam_appid.txt").write_text("480")
    result=convert(tmp_path,train)
    m=json.loads((result.output_path/".megcfbt/package.json").read_text())
    assert steam_library.identity(m)==3711590 and m.get("steam_identity") is None


@pytest.mark.skipif(__import__("sys").platform != "linux", reason="Native symlink launcher safety runs on Linux")
def test_native_api_bootstrap_is_idempotent_and_rejects_unexpected_paths(tmp_path,train):
    import os
    import subprocess
    result=convert(tmp_path,train);root=result.output_path
    provider=tmp_path/"installed-steam";provider.mkdir();(provider/"libsteam_api.so").write_bytes(elf())
    launcher=root/"launch.sh";launcher.write_text(launcher.read_text().replace('/opt/steamvr/bin/linuxarm64',str(provider)))
    (root/"godot.arm64").write_text('#!/usr/bin/env bash\nprintf launched\n');(root/"godot.arm64").chmod(0o755)
    env=dict(os.environ,MEGCFBT_FRAME_ENV_IMPORTED="1",DISPLAY=":test")
    before=snapshot(provider)
    for _ in range(2):
        r=subprocess.run(['bash',str(launcher)],env=env,text=True,capture_output=True)
        assert r.returncode==0 and r.stdout=='launched'
    api=root/'game/addons/godotsteam/linuxarm64/libsteam_api.so'
    assert api.is_symlink() and api.resolve()==provider/'libsteam_api.so'
    api.unlink();api.write_bytes(b'Unexpected user file')
    r=subprocess.run(['bash',str(launcher)],env=env,text=True,capture_output=True)
    assert r.returncode!=0 and 'Unexpected native Steam API path' in r.stderr
    assert api.read_bytes()==b'Unexpected user file' and snapshot(provider)==before
    api.unlink()
    parent=api.parent;parent.rename(parent.with_name('original-linuxarm64'));parent.symlink_to(provider,target_is_directory=True)
    r=subprocess.run(['bash',str(launcher)],env=env,text=True,capture_output=True)
    assert r.returncode!=0 and 'Unsafe Steam API directory' in r.stderr
    assert snapshot(provider)==before
