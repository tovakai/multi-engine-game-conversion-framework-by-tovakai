from dataclasses import replace
from pathlib import Path
from megcfbt.native_backend import NativeBuildError


def inspect_game(root: Path):
    from megcfbt.router import _rpgm_summary
    result = _rpgm_summary(root)
    if result is not None and result.engine == 'construct':
        return replace(result, backend='constructframe')
    return None


def build_game(source: Path, **kwargs):
    from rpgmframe.builder import build_game as build_shared
    from rpgmframe.source import prepare_source
    with prepare_source(source) as prepared:
        if inspect_game(prepared.root) is None:
            raise NativeBuildError('Source is not a supported Construct export.')
    kwargs.pop('steam_app_id', None)
    return build_shared(source, **kwargs)
