from pathlib import Path
import json,struct,hashlib

def write_pack(destination: Path, files: dict[str,bytes]):
    """Godot 4.1 PCK v2 with unchanged base pack and explicit replacement entries."""
    entries=[]
    directory_size=100
    for name,data in sorted(files.items()):
        encoded=('res://'+name).encode('utf-8')
        encoded+=b'\0' * ((-len(encoded)) % 4)
        directory_size+=4+len(encoded)+16+16+4
        entries.append((encoded,data))
    offset=(directory_size+15)//16*16
    directory=bytearray(struct.pack('<6IQ',0x43504447,2,4,1,4,0,0)+bytes(64)+struct.pack('<I',len(entries)))
    blocks=[]
    for encoded,data in entries:
        directory+=struct.pack('<I',len(encoded))+encoded+struct.pack('<QQ',offset,len(data))+hashlib.md5(data).digest()+struct.pack('<I',0)
        padding=(-len(data))%16
        blocks.append(data+bytes(padding))
        offset+=len(data)+padding
    with destination.open('wb') as stream:
        stream.write(directory)
        stream.write(bytes((-len(directory))%16))
        for block in blocks:stream.write(block)

def extension(entry,library,dependencies=()):
    text='[configuration]\nentry_symbol="'+entry+'"\ncompatibility_minimum=4.1\n[libraries]\nlinux.release="res://'+library+'"\nlinux.debug="res://'+library+'"\n'
    if dependencies:
        text+='[dependencies]\nlinux={'+', '.join('"res://'+path+'":""' for path in dependencies)+'}\n'
    return text.encode()

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    output=Path('build/until-then-overlay');output.mkdir(parents=True,exist_ok=True)
    descriptors={
        'addons/internal/internal.gdextension':extension('internal_library_init','addons/internal/linux/libinternal.so'),
        'addons/jsonutils/jsonutils.gdextension':extension('jsonutils_library_init','addons/jsonutils/linux/libjsonutils.so'),
        'addons/inkcpp/inkcpp.gdextension':extension('inkcpp_library_init','addons/inkcpp/linux/libinkcpp.so'),
        'addons/threen/threen.gdextension':extension('threen_library_init','addons/threen/linux/libthreen.so'),
        'addons/godotsteam/godotsteam.gdextension':extension('godotsteam_init','addons/godotsteam/linux/libgodotsteam.so',['addons/godotsteam/linux/libsteam_api.so']),
        'addons/fmod/fmod.gdextension':extension('fmod_library_init','addons/fmod/native/linux/libfmod.release.so',['addons/fmod/native/linux/libfmod.so','addons/fmod/native/linux/libfmodstudio.so']),
    }
    # One custom-engine-only thumbnail call uses a fifth loader parameter.
    # Existing-resource parity was measured in the original engine; scheduling
    # semantics remain unverified. Keep this adaptation experimental and hash-gated.
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-pack',type=Path)
    args=parser.parse_args()
    if args.source_pack:
        profile=json.loads((root/'source-profile.json').read_text())
        sha=hashlib.sha256()
        with args.source_pack.open('rb') as stream:
            while chunk:=stream.read(8*1024*1024):sha.update(chunk)
        if sha.hexdigest()!=profile['source_pack_sha256']:raise ValueError('Unverified game pack')
        name='res://ui/components/Game/SceneView/SceneView.gd'
        data=None
        with args.source_pack.open('rb') as stream:
            header=stream.read(96)
            if struct.unpack('<6I',header[:24])!=(0x43504447,2,4,1,4,0):raise ValueError('Unexpected pack layout')
            base=struct.unpack_from('<Q',header,24)[0]
            count=struct.unpack('<I',stream.read(4))[0]
            if count>1000000:raise ValueError('Unbounded pack directory')
            for _ in range(count):
                length=struct.unpack('<I',stream.read(4))[0]
                if length>65536:raise ValueError('Unsafe pack path')
                current=stream.read(length).rstrip(b'\0').decode()
                offset,size=struct.unpack('<QQ',stream.read(16))
                stream.read(16)
                flags=struct.unpack('<I',stream.read(4))[0]
                if current==name:
                    if flags or size>1024*1024:raise ValueError('Unexpected script encoding')
                    stream.seek(base+offset)
                    data=stream.read(size)
                    break
        if data is None:raise ValueError('Expected thumbnail script missing')
        old=b'ResourceLoader.load_threaded_request(_path, "", false, ResourceLoader.CACHE_MODE_REUSE, true)'
        new=b'ResourceLoader.load_threaded_request(_path, "", false, ResourceLoader.CACHE_MODE_REUSE)'
        if data.count(old)!=1:raise ValueError('Unexpected custom loader call')
        descriptors[name.removeprefix('res://')]=data.replace(old,new)
    write_pack(output/'untilthen-native-overlay.pck',descriptors)
    (output/'overlay-manifest.json').write_text(json.dumps({'status':'experimental-not-gameplay-verified','files':{name:hashlib.sha256(data).hexdigest() for name,data in descriptors.items()}},indent=2))
    print(output/'untilthen-native-overlay.pck')
