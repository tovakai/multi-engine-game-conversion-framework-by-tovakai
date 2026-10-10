"""Compatibility for stock Construct desktop exports on ARM64 NW.js."""
import json
from pathlib import Path
import re


def install_construct3_compatibility(payload: Path, package_path: Path) -> list[str]:
    """Use the export's DOM fallback for Chromium local-worker origin failures."""
    main = payload / 'scripts/main.js'
    if not main.is_file():
        return []
    text = main.read_text(encoding='utf-8')
    if not re.search(r'new\s+self\.RuntimeInterface\s*\(', text):
        return []
    updated, count = re.subn(r'\bconst\s+enableWorker\s*=\s*true\b',
                            'const enableWorker=false', text)
    if count != 1:
        return []
    main.write_text(updated, encoding='utf-8', newline='\n')
    package = json.loads(package_path.read_text(encoding='utf-8'))
    args = package.get('chromium-args')
    if isinstance(args, str):
        package['chromium-args'] = re.sub(r'(?<!\S)--enable-node-worker(?!\S)\s*', '', args).strip()
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=4) + '\n', encoding='utf-8')
    return ['Construct 3 uses its DOM runtime fallback to avoid local-worker origin failures on modern NW.js.']
