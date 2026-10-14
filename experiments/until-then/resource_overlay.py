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
    write_pack(output/'untilthen-native-overlay.pck',descriptors)
    (output/'overlay-manifest.json').write_text(json.dumps({'status':'experimental-not-gameplay-verified','files':{name:hashlib.sha256(data).hexdigest() for name,data in descriptors.items()}},indent=2))
    print(output/'untilthen-native-overlay.pck')
