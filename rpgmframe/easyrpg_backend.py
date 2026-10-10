"""Native Linux RPG Maker 2000/2003 packages using installed EasyRPG."""
from pathlib import Path
import shutil
import uuid

from rpgmframe.launchers import _FRAME_ENV_PREAMBLE
from rpgmframe.models import BuildResult, EngineVariant


def find_easyrpg_root(root: Path) -> Path | None:
    level = [root]
    for _ in range(9):
        matches = []
        next_level = []
        for candidate in level:
            try:
                children = list(candidate.iterdir())
                names = {p.name.casefold(): p for p in children if p.is_file()}
                db, tree = names.get('rpg_rt.ldb'), names.get('rpg_rt.lmt')
                if db and tree:
                    with db.open('rb') as handle:
                        valid_db = handle.read(12) == b'\x0bLcfDataBase'
                    with tree.open('rb') as handle:
                        valid_tree = handle.read(11) == b'\x0aLcfMapTree'
                    if valid_db and valid_tree:
                        matches.append(candidate)
                next_level.extend(p for p in children if p.is_dir() and not p.is_symlink()
                                  and p.name.casefold() not in {'.git', '__macosx'})
            except OSError:
                continue
        if matches:
            return matches[0] if len(matches) == 1 else None
        level = next_level[:4096]
    return None


def build_easyrpg_game(*, source_path, output_path, inspection, force=False, progress=None):
    from rpgmframe.builder import BuildError, _install_staging
    source = inspection.game_root
    if source is None or source == output_path or source in output_path.parents or output_path in source.parents:
        raise BuildError('EasyRPG output must be separate from the game source.')
    if output_path.exists() and not force:
        raise BuildError(f'Output already exists: {output_path}. Pass --force to replace it.')
    staging = output_path.parent / f'.{output_path.name}.tmp-{uuid.uuid4().hex[:8]}'
    try:
        if progress:
            progress('Copying RPG Maker 2000/2003 data for native EasyRPG')
        def ignore_windows_tools(directory, names):
            # EasyRPG reads RPG_RT.exe as data to identify engine patches/version.
            # It is never executed, but deleting it loses useful compatibility evidence.
            return [name for name in names if name == '.git' or
                    (name.casefold().endswith(('.exe', '.dll')) and name.casefold() != 'rpg_rt.exe')]
        shutil.copytree(source, staging / 'game', ignore=ignore_windows_tools)
        launcher = staging / 'launch.sh'
        launcher.write_text(_FRAME_ENV_PREAMBLE + '''cd "$ROOT/game"
if command -v easyrpg-player >/dev/null 2>&1; then
    exec easyrpg-player --project-path "$ROOT/game" "$@"
fi
if command -v flatpak >/dev/null 2>&1 && flatpak info --arch=aarch64 org.easyrpg.player >/dev/null 2>&1; then
    exec flatpak run --arch=aarch64 --filesystem="$ROOT/game" --env=RPG_GAME_PATH="$ROOT/game" org.easyrpg.player --project-path "$ROOT/game" "$@"
fi
echo "Install native EasyRPG Player first: flatpak install --user --arch=aarch64 flathub org.easyrpg.player" >&2
exit 127
''', encoding='utf-8', newline='\n')
        launcher.chmod(0o755)
        _install_staging(staging, output_path, force=force)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return BuildResult(success=True, source_path=source_path, output_path=output_path,
                       runtime_path=Path('org.easyrpg.player'), launcher_path=output_path / 'launch.sh',
                       engine=EngineVariant.RPG_2K, engine_version=None, game_name=inspection.game_name,
                       runtime_architecture='aarch64',
                       warnings=['Requires native EasyRPG Player installed on the target (system or aarch64 Flatpak).',
                                 'Windows engine patches/plugins are not carried over; verify gameplay.'])
