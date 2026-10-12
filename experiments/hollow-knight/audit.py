"""Read-only dependency audit of an owner-supplied Hollow Knight installation.

Requires dnfile==0.18.0, dncil==1.0.2 and pefile==2024.8.26. No game code is loaded.
The call listings describe static references, not runtime reachability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import dnfile
import pefile
from dncil.cil.body.reader import read_method_body_from_bytes
from dncil.clr.token import Token, StringToken


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def text(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return str(value)


def native_info(path, root):
    with pefile.PE(str(path)) as pe:
        return {
            'path': path.relative_to(root).as_posix(), 'sha256': sha256(path),
            'machine': hex(pe.FILE_HEADER.Machine),
            'imports': {text(entry.dll): [text(s.name) if s.name else f'ordinal:{s.ordinal}'
                                        for s in entry.imports]
                        for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', [])},
            'delay_imports': {text(entry.dll): [text(s.name) if s.name else f'ordinal:{s.ordinal}'
                                              for s in entry.imports]
                              for entry in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', [])},
            'exports': [text(s.name) if s.name else f'ordinal:{s.ordinal}' for s in
                        getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', [])],
        }


def managed_info(path, root, disassemble=False):
    pe = dnfile.dnPE(str(path), clr_lazy_load=True)
    try:
        if pe.net is None or pe.net.mdtables is None:
            raise ValueError(f'Not a managed assembly: {path}')
        tables = pe.net.mdtables
        methods, fields = {}, {}
        for row in tables.TypeDef.rows if tables.TypeDef else []:
            owner = f'{row.TypeNamespace}.{row.TypeName}'.lstrip('.')
            methods.update({index.row_index: f'{owner}::{index.row.Name}' for index in row.MethodList})
            fields.update({index.row_index: f'{owner}::{index.row.Name}' for index in row.FieldList})
        pinvokes = []
        for row in tables.ImplMap.rows if tables.ImplMap else []:
            pinvokes.append({'library': str(row.ImportScope.row.Name),
                             'entry_point': str(row.ImportName),
                             'method': methods.get(row.MemberForwarded.row_index, str(row.MemberForwarded.row.Name)),
                             'method_token': f'0x06000000+{row.MemberForwarded.row_index}',
                             'signature_hex': row.MemberForwarded.row.Signature.value.hex(),
                             'mapping_flags': str(row.MappingFlags)})
        external_members = []
        for row in tables.MemberRef.rows if tables.MemberRef else []:
            owner = row.Class.row
            if hasattr(owner, 'TypeNamespace'):
                external_members.append(f'{owner.TypeNamespace}.{owner.TypeName}::{row.Name}'.lstrip('.'))
        report = {'path': path.relative_to(root).as_posix(), 'sha256': sha256(path),
                  'cor_flags': hex(pe.net.struct.Flags), 'pinvokes': pinvokes,
                  'references': [str(row.Name) for row in tables.AssemblyRef.rows] if tables.AssemblyRef else [],
                  'external_members': external_members if disassemble else []}
        if not disassemble:
            return report

        def resolve(operand):
            if isinstance(operand, StringToken):
                return text(pe.net.user_strings.get(operand.rid).value)
            if not isinstance(operand, Token):
                return str(operand)
            table, rid = operand.table, operand.rid
            if table == 6:
                return methods.get(rid, str(operand))
            if table == 4:
                return fields.get(rid, str(operand))
            if table in {1, 2}:
                row = (tables.TypeRef if table == 1 else tables.TypeDef).rows[rid - 1]
                return f'{row.TypeNamespace}.{row.TypeName}'.lstrip('.')
            if table == 10:
                row = tables.MemberRef.rows[rid - 1]
                owner = row.Class.row
                if hasattr(owner, 'TypeName'):
                    return f'{owner.TypeNamespace}.{owner.TypeName}::{row.Name}'.lstrip('.')
                return str(row.Name)
            return str(operand)

        selected = {'InControl.InControlManager', 'InControl.InputManager',
                    'InControl.NativeInputDeviceManager', 'InControl.XInputDeviceManager',
                    'InControl.XInputDevice', 'InControl.Native', 'Platform',
                    'DesktopPlatform', 'SteamOnlineSubsystem', 'GOGGalaxyOnlineSubsystem',
                    'GameCoreOnlineSubsystem', 'InControl.NewUnityInputDeviceManager',
                    'InControl.NewUnityInputDevice'}
        bodies, errors = {}, []
        for rid, row in enumerate(tables.MethodDef.rows, 1):
            label = methods.get(rid, str(row.Name))
            if label.split('::')[0] not in selected or not row.Rva:
                continue
            try:
                body = read_method_body_from_bytes(pe.get_data(row.Rva, 1024 * 1024))
                bodies[label] = [{'offset': ins.offset, 'opcode': str(ins.opcode),
                                  'operand': resolve(ins.operand) if ins.operand is not None else None}
                                 for ins in body.instructions]
            except Exception as exc:
                errors.append({'method': label, 'error': str(exc)})
        report['selected_method_il'] = bodies
        report['il_errors'] = errors
        return report
    finally:
        pe.close()


def audit(root):
    data = root / 'hollow_knight_Data'
    if not (data / 'Managed/Assembly-CSharp.dll').is_file():
        raise ValueError('Expected a Hollow Knight Mono installation.')
    assemblies, errors = [], []
    for path in sorted((data / 'Managed').glob('*.dll')):
        try:
            assemblies.append(managed_info(path, root, path.name == 'Assembly-CSharp.dll'))
        except Exception as exc:
            errors.append({'path': path.relative_to(root).as_posix(), 'error': str(exc)})
    native = [native_info(path, root) for path in sorted((data / 'Plugins').rglob('*.dll'))]
    return {'schema': 1, 'source': str(root), 'scope': 'Static metadata and selected method IL; no execution or complete call graph.',
            'managed': assemblies, 'native_plugins': native, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.source.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    calls = [row for assembly in report['managed'] for row in assembly['pinvokes']]
    libraries = sorted({row['library'] for row in calls})
    print(json.dumps({'assemblies': len(report['managed']), 'pinvokes': len(calls),
                      'native_libraries': libraries, 'errors': report['errors'],
                      'output': str(args.output)}, indent=2))
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
