"""Regression tests for games bundling Ren'Py 7 and 8 version tuples."""

from renframe.detector import strategy_renpy_init
from renframe.inspect_service import inspect_game


REN_SCRIPT = """# Version information.
try:
    from renpy.vc_version import vc_version
except ImportError:
    vc_version = 0

if PY2:
    version_tuple = (7, 4, 11, vc_version)
else:
    version_tuple = (8, 0, 0, vc_version)

# A string giving the version number only (8.0.1.123), with a suffix if needed.
version_only = ".".join(str(i) for i in version_tuple)
version = "Ren'Py " + version_only
"""


def make_game(tmp_path, runtime: str):
    root = tmp_path / "Everlasting Summer"
    (root / "game").mkdir(parents=True)
    (root / "game" / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    (root / "renpy").mkdir()
    (root / "renpy" / "__init__.py").write_text(REN_SCRIPT, encoding="utf-8")
    (root / "renpy" / "vc_version.py").write_text("vc_version = 2266\n", encoding="utf-8")
    (root / "lib" / runtime).mkdir(parents=True)
    return root


def test_py2_layout_selects_renpy_7_not_version_example(tmp_path):
    root = make_game(tmp_path, "python2.7")
    hint = strategy_renpy_init(root)
    assert hint is not None
    assert (hint.version, hint.generation, hint.confidence) == ("7.4.11", 7, "high")

    inspection = inspect_game(root)
    assert inspection.renpy_version == "7.4.11"
    assert inspection.generation == 7
    assert any(h.source == "lib/" and h.generation == 7 for h in inspection.version_hints)


def test_py3_layout_selects_renpy_8(tmp_path):
    root = make_game(tmp_path, "python3.9")
    hint = strategy_renpy_init(root)
    assert hint is not None
    assert (hint.version, hint.generation) == ("8.0.0", 8)


def test_ambiguous_dual_layout_does_not_guess(tmp_path):
    root = make_game(tmp_path, "python2.7")
    (root / "lib" / "python3.9").mkdir()
    assert strategy_renpy_init(root) is None


def test_dual_tuples_without_runtime_do_not_guess(tmp_path):
    root = make_game(tmp_path, "python2.7")
    (root / "lib" / "python2.7").rmdir()
    assert strategy_renpy_init(root) is None


def test_comments_are_not_version_evidence(tmp_path):
    root = make_game(tmp_path, "python2.7")
    (root / "renpy" / "__init__.py").write_text(
        "# A string giving the version number only (8.0.1.123)\n"
        "version = 'Ren' + get_version()\n",
        encoding="utf-8",
    )
    assert strategy_renpy_init(root) is None


def test_single_literal_tuple_is_accepted_without_runtime_layout(tmp_path):
    root = make_game(tmp_path, "python2.7")
    (root / "lib" / "python2.7").rmdir()
    (root / "renpy" / "__init__.py").write_text(
        "version_tuple = (7, 3, 5, vc_version)\n",
        encoding="utf-8",
    )
    hint = strategy_renpy_init(root)
    assert hint is not None and hint.version == "7.3.5"


def test_literal_version_assignment_is_valid_evidence(tmp_path):
    root = make_game(tmp_path, "python2.7")
    (root / "renpy" / "__init__.py").write_text(
        '# Example (8.0.1.123) is not a version.\nversion = "7.4.11"\n',
        encoding="utf-8",
    )
    hint = strategy_renpy_init(root)
    assert hint is not None and hint.version == "7.4.11"


def test_conflicting_literal_tuple_and_runtime_does_not_guess(tmp_path):
    root = make_game(tmp_path, "python2.7")
    (root / "renpy" / "__init__.py").write_text(
        "version_tuple = (8, 0, 0, vc_version)\n",
        encoding="utf-8",
    )
    assert strategy_renpy_init(root) is None
