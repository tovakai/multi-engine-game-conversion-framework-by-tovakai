import io
import hashlib
import json
import tarfile
from pathlib import Path
from rpgmframe import godot_runtime_download as download
from rpgmframe.godot_custom_runtime import GODOTSTEAM_472_RECIPE, GODOTSTEAM_351_RECIPE, worker_script_for
from rpgmframe.launchers import godot_launcher_body


def test_selects_arm64_template_and_tracks_adjacent_loading(tmp_path,monkeypatch):
    elf = bytearray(64)
    elf[:6] = b'\x7fELF\x02\x01'
    elf[18:20] = (183).to_bytes(2,'little')
    entry = download.recipe_entry(GODOTSTEAM_472_RECIPE)
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed,mode='w:xz') as archive:
        for name,value in {entry['binary']:bytes(elf),entry['steam_library']:bytes(elf),
                           'linux64/unwanted':b'x86 library','../never-extracted':b'other platform metadata'}.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            archive.addfile(member,io.BytesIO(value))
    data = packed.getvalue()
    entry['sha256'] = hashlib.sha256(data).hexdigest()
    monkeypatch.setitem(download.UPSTREAM_RECIPES,GODOTSTEAM_472_RECIPE,entry)
    monkeypatch.setattr(download,'_cache_root',lambda:tmp_path/'cache')
    class Response(io.BytesIO):
        headers = {}
    monkeypatch.setattr(download.urllib.request,'urlopen',lambda *args,**kwargs:Response(data))
    result = download.ensure_downloaded_runtime(GODOTSTEAM_472_RECIPE)
    metadata = json.loads((result/'runtime.json').read_text())
    assert metadata['pack_loading'] == 'adjacent'
    assert {p.name for p in result.iterdir()} == {'godot.arm64','libsteam_api.so','runtime.json'}
    assert download._validate(result,GODOTSTEAM_472_RECIPE)
    (result/'libsteam_api.so').write_bytes(bytes(elf)+b'accidentally changed')
    assert not download._validate(result,GODOTSTEAM_472_RECIPE)


def test_adjacent_launcher_does_not_use_rejected_path_override():
    text = godot_launcher_body('game/SpaceIdle.pck',adjacent_pack=True)
    assert '--main-pack' not in text
    assert 'exec "$ROOT/godot.arm64" "$@"' in text


def test_351_recipe_does_not_apply_37_specific_canvas_patch():
    worker = worker_script_for(GODOTSTEAM_351_RECIPE)
    assert 'Applying Godot 3.x CanvasItem cast fix' not in worker
    assert 'Restoring native Steam networking C++ helpers' in worker
    assert 'release-safe Variant missing-method guard' in worker


def test_351_worker_embedded_python_is_valid():
    # The worker runs remotely without importing the converter package. Validate
    # every emitted Python block, including the legacy Steam API adapter.
    import re
    worker = worker_script_for(GODOTSTEAM_351_RECIPE)
    blocks = re.findall(r"python3[^\n]*<<'([^']+)'\n(.*?)\n\1", worker, re.S)
    assert blocks
    assert 'steamInitLegacy' in worker
    for delimiter, source in blocks:
        compile(source, '<worker-' + delimiter + '>', 'exec')
