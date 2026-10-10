import importlib.util
import marshal
from pathlib import Path

from megcfbt.router import inspect_source
from renframe.detector import strategy_vc_version_bytecode


def write_bytecode(root: Path, source: str, magic=importlib.util.MAGIC_NUMBER):
    (root / 'renpy').mkdir(exist_ok=True)
    (root / 'renpy/vc_version.pyc').write_bytes(magic + b'\0' * 12 + marshal.dumps(compile(source, 'vc_version.py', 'exec')))


def test_bytecode_only_engine_detected_without_execution(tmp_path):
    (tmp_path / 'game').mkdir()
    (tmp_path / 'lib/py3-windows-x86_64').mkdir(parents=True)
    (tmp_path / 'renpy').mkdir()
    (tmp_path / 'renpy/__init__.pyc').write_bytes(b'fixture')
    write_bytecode(tmp_path, "version = '8.5.3.26051504'\nraise RuntimeError('must never execute')\n")
    result = inspect_source(tmp_path)
    assert result.engine == 'renpy' and result.engine_version == '8.5.3'
    assert result.buildable


def test_foreign_bytecode_is_not_guessed(tmp_path):
    write_bytecode(tmp_path, "version = '8.5.3'", magic=b'BAD!')
    assert strategy_vc_version_bytecode(tmp_path) is None


def test_unrelated_constant_is_not_version_evidence(tmp_path):
    write_bytecode(tmp_path, "example = '8.5.3'\nversion = str(1)")
    assert strategy_vc_version_bytecode(tmp_path) is None


def test_truncated_bytecode_is_not_version_evidence(tmp_path):
    (tmp_path / 'renpy').mkdir()
    (tmp_path / 'renpy/vc_version.pyc').write_bytes(importlib.util.MAGIC_NUMBER + b'\0' * 12)
    assert strategy_vc_version_bytecode(tmp_path) is None
