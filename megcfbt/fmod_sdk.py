"""Shared SDK selection memory; each backend retains its own checksum gate."""
import json
import os
from pathlib import Path

FMOD_URL = 'https://www.fmod.com/download#fmodengine'

def settings_path():
    return Path(os.environ.get('APPDATA', Path.home()/'.config'))/'megcfbt/fmod/sdk.json'

def remembered_sdk():
    shared = settings_path()
    for record in (shared, shared.parents[1]/'sts2/sdk.json'):
        try:
            value = json.loads(record.read_text())['sdk_file']
            if isinstance(value, str) and value:
                return Path(value)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None

def remember_sdk(path):
    record = settings_path()
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({'sdk_file': str(Path(path).resolve())})+'\n')
