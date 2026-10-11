from pathlib import Path
from unittest import mock
import pytest
from megcfbt.sts2_backend import module


def test_retail_spine_uses_its_actual_manifest_directory(tmp_path):
    converter=module('convert_sts2');pack=module('patch_pack');verify=module('verify_output')
    profile=converter.load_profile()
    import json
    retail=json.loads((Path(converter.__file__).parent/'converter_profile_v107.json').read_bytes())
    spine=next(p for p in retail['native_files'] if p['provider_name'].startswith('libspine'))
    raw=b'[libraries]\nlinux.release.arm64 = "linux/libspine_godot.linux.template_release.arm64.so"\n'
    target=tmp_path/spine['destination'];target.parent.mkdir(parents=True);target.write_bytes(b'ELF fixture')
    with mock.patch.object(verify,'inspect',side_effect=lambda path:{'elf_machine':183} if path.is_file() else (_ for _ in ()).throw(FileNotFoundError(path))):
        assert pack.validate_native_binding(tmp_path,'addons/spine/spine_godot_extension.gdextension',raw)['library']==spine['destination']
        target.unlink()
        wrong=tmp_path/'bin/linux'/target.name;wrong.parent.mkdir(parents=True);wrong.write_bytes(b'ELF fixture')
        with pytest.raises(FileNotFoundError):
            pack.validate_native_binding(tmp_path,'addons/spine/spine_godot_extension.gdextension',raw)


def test_native_binding_refuses_traversal_and_wrong_architecture(tmp_path):
    pack=module('patch_pack');verify=module('verify_output')
    with pytest.raises(ValueError): pack.validate_native_binding(tmp_path,'addons/spine/ext.gdextension',b'linux.release.arm64 = "../../escape.so"\n')
    with mock.patch.object(verify,'inspect',return_value={'elf_machine':62}):
        with pytest.raises(ValueError,match='AArch64'): pack.validate_native_binding(tmp_path,'bin/ext.gdextension',b'linux.release.arm64 = "linux/lib.so"\n')
