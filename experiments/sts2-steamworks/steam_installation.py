"""Read-only Steam installation prerequisite for the existing STS2 launcher."""

from pathlib import Path, PurePosixPath
import re

APPID = '2868840'


def keyvalues(path):
    """Parse bounded text KeyValues manifests, including comments and escaped paths."""
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Steam manifest exceeds limit')
    text = path.read_text(encoding='utf-8-sig')
    token = re.compile(r'\s+|//[^\n]*|[{}]|"(?:[^"\\]|\\.)*"')
    tokens = []
    offset = 0
    while offset < len(text):
        match = token.match(text, offset)
        if match is None:
            raise ValueError('Malformed Steam manifest')
        value = match.group()
        offset = match.end()
        if not value.isspace() and not value.startswith('//'):
            tokens.append(value)

    def string(value):
        if not value.startswith('"'):
            raise ValueError('Malformed Steam manifest key/value')
        return re.sub(r'\\([\\"])', r'\1', value[1:-1])

    def object_at(index, depth=0):
        if depth > 16:
            raise ValueError('Steam manifest nesting exceeds limit')
        result = {}
        while index < len(tokens) and tokens[index] != '}':
            key = string(tokens[index]).lower()
            index += 1
            if key in result or index >= len(tokens):
                raise ValueError('Duplicate or incomplete Steam manifest entry')
            if tokens[index] == '{':
                value, index = object_at(index + 1, depth + 1)
            else:
                value = string(tokens[index])
                index += 1
            result[key] = value
        if depth:
            if index >= len(tokens):
                raise ValueError('Unclosed Steam manifest object')
            index += 1
        return result, index

    result, consumed = object_at(0)
    if consumed != len(tokens):
        raise ValueError('Unexpected Steam manifest closing brace')
    return result


def require_installed(home=None):
    """Require a fully installed official entry; this does not verify ownership."""
    home = Path.home() if home is None else Path(home)
    roots = [home / '.local/share/Steam', home / '.steam/steam', home / '.steam/root']
    libraries = set()
    problems = []
    for root in roots:
        libraries.add(root.resolve())
        for path in (root / 'steamapps/libraryfolders.vdf', root / 'config/libraryfolders.vdf'):
            if not path.is_file():
                continue
            try:
                entries = keyvalues(path).get('libraryfolders', {})
                if not isinstance(entries, dict):
                    raise ValueError('Malformed Steam library list')
                for number, entry in entries.items():
                    if not number.isdigit():
                        continue
                    value = entry.get('path') if isinstance(entry, dict) else entry
                    if isinstance(value, str) and Path(value).is_absolute():
                        libraries.add(Path(value).resolve())
            except (OSError, ValueError) as error:
                problems.append(str(path) + ': ' + str(error))
    for library in sorted(libraries):
        manifest = library / ('steamapps/appmanifest_' + APPID + '.acf')
        if not manifest.is_file():
            continue
        try:
            state = keyvalues(manifest).get('appstate', {})
            if not isinstance(state, dict) or state.get('appid') != APPID:
                raise ValueError('STS2 Steam manifest has a different AppID')
            if state.get('stateflags') != '4':
                raise ValueError('STS2 is not fully installed/updated in Steam')
            folder = state.get('installdir', '')
            name = PurePosixPath(folder)
            if not folder or name.parts != (folder,) or folder in {'.', '..'} or '\\' in folder:
                raise ValueError('Invalid Steam installation folder')
            installation = library / 'steamapps/common' / folder
            if not (installation / 'SlayTheSpire2.pck').is_file():
                raise ValueError('STS2 Steam installation files are missing')
            return {'appid': APPID, 'manifest': str(manifest), 'installation': str(installation)}
        except (OSError, ValueError) as error:
            problems.append(str(error))
    detail = ' (' + '; '.join(problems) + ')' if problems else ''
    raise ValueError('Slay the Spire 2 must be installed and fully updated through Steam on this Frame '
                     'before compilation. Open its Steam Library entry and click Install, then rerun '
                     'sh ./install.sh. This launcher needs the actual STS2 Steam entry; a non-Steam '
                     'shortcut will not work. Your prepared files, compiled game and build cache are retained.' + detail)
