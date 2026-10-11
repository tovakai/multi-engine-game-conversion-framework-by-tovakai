from pathlib import Path
import marshal
import struct
import pytest
from renframe.bytecode_metadata import literal_assignments
from renframe.detector import strategy_vc_version_bytecode
from renframe.source_safety import validate_copy_tree
from renframe.inspect_service import inspect_game
from megcfbt.router import inspect_source
from renframe.builder import build_game, BuildError, _validate_runtime_inspection
from renframe.runtime import inspect_runtime


def game(root):
    (root/'game').mkdir(parents=True)
    (root/'renpy').mkdir()
    (root/'renpy/__init__.py').write_text('version_tuple = (8, 0, 3, 1)\n')
    (root/'lib/py3-windows-x86_64').mkdir(parents=True)
    (root/'game/script.rpy').write_text('label start:\n    "test"\n')
    return root


def test_mac_resources_export_discovered_with_sibling_files(tmp_path):
    root=tmp_path/'export'
    source=game(root/'My Game.app/Contents/Resources')
    (root/'README.txt').write_text('manual')
    (source.parent/'Info.plist').write_text('metadata')
    result=inspect_source(root)
    assert result.engine_version=='8.0.3' and result.game_name=='My Game'


def test_multiple_renpy_games_require_selection(tmp_path):
    game(tmp_path/'a')
    game(tmp_path/'b')
    assert inspect_source(tmp_path).compatibility=='ambiguous'


def test_foreign_python39_version_metadata_is_read_without_execution(tmp_path):
    root=tmp_path/'renpy'
    root.mkdir()
    # A released Python 3.9 code header and literal assignment metadata.
    body=b'c'+struct.pack('<6i',0,0,0,0,1,0)
    body+=marshal.dumps(bytes([100,0,90,0,100,1,90,1]),2)
    body+=marshal.dumps(('8.0.3.22090809',False),2)
    body+=marshal.dumps(('version','nightly'),2)
    path=root/'vc_version.pyc'
    path.write_bytes(struct.pack('<H',3425)+b'\r\n'+b'\0'*12+body)
    assert literal_assignments(path)=={'version':'8.0.3.22090809','nightly':False}
    assert strategy_vc_version_bytecode(tmp_path).version=='8.0.3'


def test_conflicting_engine_metadata_does_not_pick_a_version(tmp_path):
    source=game(tmp_path/'source')
    (source/'renpy/vc_version.py').write_text("version = '8.5.3'\n")
    result=inspect_game(source)
    assert result.renpy_version is None
    assert result.compatibility.value=='UNKNOWN_RENPY_VERSION'
    assert any('Conflicting' in warning for warning in result.warnings)


def test_overlapping_output_rejected_before_download(tmp_path):
    source=game(tmp_path/'source')
    class Manager:
        def platform_path(self, release, tag):
            return tmp_path/'runtime/py3-linux-aarch64'
        def ensure_platform(self,*a,**k):
            pytest.fail('must reject paths before network or cache mutation')
    with pytest.raises(BuildError,match='conflicts'):
        build_game(source,output=source/'output',runtime_manager=Manager())


def test_disguised_x86_python_in_arm_directory_is_rejected(tmp_path):
    runtime=game(tmp_path/'runtime')
    arm=runtime/'lib/py3-linux-aarch64'
    arm.mkdir()
    (runtime/'renpy.py').write_text('# bootstrap')
    header=bytearray(20)
    header[:4]=b'\x7fELF'
    header[4:6]=bytes([2,1])
    struct.pack_into('<H',header,18,62)
    (arm/'python').write_bytes(header)
    with pytest.raises(BuildError,match='not AArch64'):
        _validate_runtime_inspection(inspect_runtime(runtime))


def symlink(link,target, directory=False):
    try:
        link.symlink_to(target,target_is_directory=directory)
    except OSError:
        pytest.skip('symlink privileges unavailable')


def test_external_source_link_rejected(tmp_path):
    root=tmp_path/'source'
    root.mkdir()
    outside=tmp_path/'outside.py'
    outside.write_text('original')
    symlink(root/'bootstrap.py',outside)
    with pytest.raises(ValueError,match='escapes'):
        validate_copy_tree(root)
    assert outside.read_text()=='original'


def test_cross_directory_link_cycle_rejected(tmp_path):
    (tmp_path/'a').mkdir()
    (tmp_path/'b').mkdir()
    symlink(tmp_path/'a/link',tmp_path/'b',True)
    symlink(tmp_path/'b/link',tmp_path/'a',True)
    with pytest.raises(ValueError,match='recursive'):
        validate_copy_tree(tmp_path)
