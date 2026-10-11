"""Explicit source identities for profiles that require a custom managed framework."""
from pathlib import Path
import hashlib,json

STARDEW_PROFILE='stardew-steam-1.6.15-net6'
STARDEW_HASHES={
    'Stardew Valley.dll':'7f1e5b8e58d2758b78570ba771bbeb03d33522f62188bf6c32edf0cf626deaee',
    'MonoGame.Framework.dll':'92e5423a5d002b399de4369e483577007274c5634745f5414fd508981b7494de',
    'StardewValley.GameData.dll':'9c03497c2d2ac24c94e2f25b3c2fc39ecde1bc97341e514c5f9fdcc1e759cb81',
}


def matches_stardew(root: Path) -> bool:
    if not (root/'Content').is_dir() or (root/'StardewModdingAPI.dll').exists():return False
    try:
        config=json.loads((root/'Stardew Valley.runtimeconfig.json').read_text())['runtimeOptions']
        if not isinstance(config,dict):return False
        frameworks=config.get('includedFrameworks',[])
        if not isinstance(frameworks,list) or config.get('tfm')!='net6.0' or not any(isinstance(f,dict) and f.get('name')=='Microsoft.NETCore.App' and f.get('version')=='6.0.32' for f in frameworks):return False
        return all(hashlib.sha256((root/name).read_bytes()).hexdigest()==digest for name,digest in STARDEW_HASHES.items())
    except (OSError,ValueError,KeyError,TypeError):return False
