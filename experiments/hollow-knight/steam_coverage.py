"""Conservative static Steam wrapper trace for this audited Hollow Knight edition."""
from __future__ import annotations

import json
from pathlib import Path

import dnfile
import pefile
from dncil.cil.body.reader import read_method_body_from_bytes
from dncil.clr.token import Token


def trace(assembly: Path, game_members: list[str], bridge: Path):
    pe = dnfile.dnPE(str(assembly), clr_lazy_load=True)
    try:
        tables = pe.net.mdtables
        owners = {m.row_index: f'{t.TypeNamespace}.{t.TypeName}'.lstrip('.')
                  for t in tables.TypeDef.rows for m in t.MethodList}
        names = {i: f'{owners[i]}::{m.Name}' for i, m in enumerate(tables.MethodDef.rows, 1)}
        # Generic Callback/CallResult references use TypeSpec, so explicitly include
        # every method of their lifecycle types rather than losing them in the trace.
        lifecycle = {'Steamworks.Callback`1', 'Steamworks.CallbackDispatcher',
                     'Steamworks.CallResult`1', 'Steamworks.CCallbackBase'}
        pending = {i for i, name in names.items() if name in game_members or owners[i] in lifecycle}
        seeds = sorted(names[i] for i in pending)
        visited, errors = set(), []
        pinvokes = {row.MemberForwarded.row_index: (str(row.ImportScope.row.Name), str(row.ImportName))
                    for row in tables.ImplMap.rows}
        required = set()
        while pending:
            rid = pending.pop()
            if rid in visited:
                continue
            visited.add(rid)
            if rid in pinvokes:
                lib, entry = pinvokes[rid]
                if lib == 'steam_api64':
                    required.add(entry)
                continue
            row = tables.MethodDef.rows[rid - 1]
            if not row.Rva:
                continue
            try:
                body = read_method_body_from_bytes(pe.get_data(row.Rva, 1024 * 1024))
                for instruction in body.instructions:
                    operand = instruction.operand
                    if not isinstance(operand, Token):
                        continue
                    table, target = operand.table, operand.rid
                    if table == 43:  # MethodSpec: follow the unspecialized method.
                        method = tables.MethodSpec.rows[target - 1].Method
                        table, target = method.table.number, method.row_index
                    if table == 6:
                        pending.add(target)
                    elif table == 10:
                        member = tables.MemberRef.rows[target - 1]
                        owner = member.Class.row
                        if hasattr(owner, 'TypeName'):
                            name = f'{owner.TypeNamespace}.{owner.TypeName}::{member.Name}'.lstrip('.')
                            pending.update(i for i, candidate in names.items() if candidate == name)
            except Exception as exc:
                errors.append({'method': names[rid], 'error': str(exc)})
        with pefile.PE(str(bridge)) as native:
            exports = {row.name.decode('ascii') for row in native.DIRECTORY_ENTRY_EXPORT.symbols if row.name}
        return {'scope': 'Static wrapper trace; reflection/dynamic reachability and ABI remain unvalidated.',
                'seeds': seeds, 'visited_methods': len(visited), 'required_exports': sorted(required),
                'missing_exports': sorted(required - exports), 'errors': errors}
    finally:
        pe.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('app_audit', type=Path)
    parser.add_argument('bridge', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    members = json.loads(args.app_audit.read_text())['external_members']
    report = trace(args.source / 'hollow_knight_Data/Managed/com.rlabrecque.steamworks.net.dll',
                   members, args.bridge)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
