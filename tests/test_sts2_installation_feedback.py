import io
from pathlib import Path
import sys
from unittest import mock

import pytest

from megcfbt.sts2_backend import module


def installed_library(root, *, flags='4', appid='2868840', folder='Slay the Spire 2', pack=True):
    steamapps = root/'steamapps'; steamapps.mkdir(parents=True, exist_ok=True)
    (steamapps/'appmanifest_2868840.acf').write_text(
        f'"AppState" {{ "appid" "{appid}" "StateFlags" "{flags}" "installdir" "{folder}" }}')
    game = steamapps/'common'/folder
    game.mkdir(parents=True, exist_ok=True)
    if pack:
        (game/'SlayTheSpire2.pck').write_bytes(b'installed Steam game fixture')
    return game


def test_installer_stops_before_package_work_or_compilation_when_steam_game_missing(tmp_path):
    installer = module('frame_install')
    with mock.patch.object(installer.platform, 'system', return_value='Linux'), \
         mock.patch.object(installer.platform, 'machine', return_value='aarch64'), \
         mock.patch.object(Path, 'home', return_value=tmp_path), \
         mock.patch.object(installer, 'verify_package', side_effect=AssertionError('Expensive package verification')), \
         mock.patch.object(installer, 'cached_build', side_effect=AssertionError('Compilation')):
        with pytest.raises(ValueError, match='click Install.*rerun'):
            installer.install(tmp_path, progress=lambda message:None)


def test_default_steam_library_and_sd_card_library_are_detected(tmp_path):
    steam = module('steam_installation')
    default = tmp_path/'.local/share/Steam'
    game = installed_library(default)
    assert steam.require_installed(tmp_path)['installation'] == str(game)
    (default/'steamapps/appmanifest_2868840.acf').unlink()
    sd_card = tmp_path/'SD Card with spaces'
    game = installed_library(sd_card)
    (default/'steamapps/libraryfolders.vdf').write_text(
        '"libraryfolders" { "0" { "path" "' + default.as_posix() + '" } '
        '"1" { "path" "' + sd_card.as_posix() + '" "apps" { "2868840" "12345" } } }')
    assert steam.require_installed(tmp_path)['installation'] == str(game)


@pytest.mark.parametrize('options', [{'flags':'1026'}, {'flags':'0'}, {'appid':'480'}, {'pack':False}])
def test_partial_stale_or_unrelated_steam_entries_are_refused(tmp_path, options):
    installed_library(tmp_path/'.local/share/Steam', **options)
    with pytest.raises(ValueError, match='must be installed and fully updated'):
        module('steam_installation').require_installed(tmp_path)


def test_malformed_steam_metadata_is_actionable_and_unmodified(tmp_path):
    default = tmp_path/'.local/share/Steam/steamapps'; default.mkdir(parents=True)
    manifest = default/'appmanifest_2868840.acf'
    original = '"AppState" { "appid" "2868840" "appid" "480" }'
    manifest.write_text(original)
    with pytest.raises(ValueError, match='Duplicate'):
        module('steam_installation').require_installed(tmp_path)
    assert manifest.read_text() == original


def test_keyvalues_comments_and_escaped_paths(tmp_path):
    path = tmp_path/'libraryfolders.vdf'
    path.write_text('// Steam library list\n"libraryfolders" { "1" { "path" "C:\\\\Games" } }')
    assert module('steam_installation').keyvalues(path)['libraryfolders']['1']['path'] == 'C:\\Games'


def test_live_compiler_output_is_reported_and_retained_on_failure(tmp_path):
    builder = module('build_native')
    events = []
    log = tmp_path/'build.log'
    args = [sys.executable, '-c', 'print("Compiling fixture.cpp", flush=True); print("compiler error", flush=True); raise SystemExit(7)']
    with pytest.raises(RuntimeError, match=r'Command failed \(7\)'):
        builder.command(args, tmp_path, log, progress=events.append)
    assert [event['message'] for event in events] == ['Compiling fixture.cpp', 'compiler error']
    assert all(event['kind'] == 'output' for event in events)
    assert 'compiler error' in log.read_text()


def test_compilation_bar_moves_without_fabricating_a_percentage():
    class Terminal(io.StringIO):
        def isatty(self):
            return True
    output = Terminal()
    meter = module('build_progress').BuildProgress(output)
    with mock.patch('time.monotonic', return_value=100):
        meter.event({'kind':'stage', 'message':'Compiling Spine'})
        meter.event({'kind':'output', 'message':'Compiling fixture.cpp'})
    meter.render(now=105)
    first = output.getvalue()
    meter.render(now=106)
    second = output.getvalue()[len(first):]
    assert first != second
    assert 'elapsed 00:05' in first
    assert '1 build messages' in first
    assert 'fixture.cpp' in first
    assert '%' not in first
    meter.event({'kind':'complete'})
    assert 'Native build verified.' in output.getvalue()
