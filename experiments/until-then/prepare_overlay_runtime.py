"""Install the small explicit resource-overlay hook into the isolated engine source.

Run only between builds. Overlay files belong to the converted package; the
original main pack remains unchanged. This is not a release backend.
"""
from pathlib import Path
import hashlib,json
source=Path.home()/'.cache/megcfbt/research/until-then/godot-4.1.4'
path=source/'core/config/project_settings.cpp'
text=path.read_text()
anchor='\t\tError err = _load_settings_text_or_binary("res://project.godot", "res://project.binary");'
replacement='''\t\t// Explicit converted-package overlay, loaded before settings and GDExtensions.
\t\tconst String megcfbt_overlay = OS::get_singleton()->get_environment("MEGCFBT_RESOURCE_OVERLAY");
\t\tif (!megcfbt_overlay.is_empty()) {
\t\t\tERR_FAIL_COND_V_MSG(!_load_resource_pack(megcfbt_overlay), ERR_CANT_OPEN,
\t\t\t\t\t"Cannot open converted resource overlay '" + megcfbt_overlay + "'.");
\t\t}

'''+anchor
if 'const String megcfbt_overlay' not in text:
 start=text.index('if (!p_main_pack.is_empty()) {')
 position=text.index(anchor,start)
 assert '_load_resource_pack(p_main_pack)' in text[start:position]
 path.with_suffix('.cpp.before-megcfbt-overlay').write_text(text)
 path.write_text(text[:position]+replacement+text[position+len(anchor):])
print('OVERLAY_HOOK_READY',hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
