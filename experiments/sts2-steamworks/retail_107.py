"""Separate exact-byte retail v0.107.1 recipe; derived through static IL evidence."""

import hashlib
import json
from pathlib import Path

from prepare_managed import arm64_metadata, prepare_pair, WINDOWS_GAME
from patch_accessors import ORIGINAL_SHA256
import patch_stats
from adapt_packed_manifests import RECIPES

HERE=Path(__file__).resolve().parent


def managed(game,wrapper):
    recipe=json.loads((HERE/'retail_107_managed_recipe.json').read_bytes())
    tagged=arm64_metadata(game,recipe['source_sha256'],recipe['tagged_sha256'])
    before=bytes.fromhex(recipe['before_hex']);after=bytes.fromhex(recipe['after_hex']);offset=recipe['offset']
    if tagged[offset:offset+len(before)]!=before: raise ValueError('Retail stats initializer differs from inspected IL')
    result=tagged[:offset]+after+tagged[offset+len(before):]
    if hashlib.sha256(result).hexdigest()!=recipe['target_sha256']: raise ValueError('Retail managed output mismatch')
    # The retail wrapper is byte-identical to the old original wrapper. Reuse its
    # independently guarded interface recipes, not the old game's offsets.
    import patch_accessors
    wrapper=arm64_metadata(wrapper,'e1cd0bf2436cefbb8bfcfcc1cea0587e5b9c740769e8340f7b9e9de72785fcf0',ORIGINAL_SHA256)
    wrapper=patch_accessors.patched_bytes(wrapper,'generic-v1')
    wrapper=patch_accessors.patched_bytes(wrapper,'client023-v2')
    wrapper=patch_stats.patched_bytes(wrapper,patch_stats.RECIPES[0])
    return {'sts2.dll':result,'Steamworks.NET.dll':wrapper}


def pack(resources):
    recipe=json.loads((HERE/'retail_107_pack_recipe.json').read_bytes())
    sha=lambda b:hashlib.sha256(b).hexdigest()
    if set(resources)!=set(recipe['unchanged'])|set(recipe['manifests']): raise ValueError('Unexpected retail extension resource set')
    for name,pin in recipe['unchanged'].items():
        if sha(resources[name])!=pin: raise ValueError('Retail preserved manifest mismatch')
    result=dict(resources);records=[]
    for name,pin in recipe['manifests'].items():
        raw=resources[name]
        if sha(raw)!=pin['source_sha256']: raise ValueError('Unknown retail manifest input')
        for before,after in RECIPES[name][2]:
            if raw.count(before)==0 and raw.count(after)==1: continue
            if raw.count(before)!=1: raise ValueError('Unexpected retail manifest anchor')
            raw=raw.replace(before,after,1)
        if sha(raw)!=pin['target_sha256']: raise ValueError('Retail manifest output mismatch')
        result[name]=raw;records.append({'path':name,'input_sha256':pin['source_sha256'],'output_sha256':pin['target_sha256'],'verified':True})
    return result,{'recipe_id':recipe['recipe'],'patches':records}


def preserved_paths():
    return json.loads((HERE/'retail_107_pack_recipe.json').read_bytes())['unchanged']
