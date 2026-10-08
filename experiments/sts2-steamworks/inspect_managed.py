#!/usr/bin/env python3
"""Read Steamworks.NET metadata and IL without executing the assembly."""

import argparse
import hashlib
import json
from pathlib import Path

import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBytes


METHODS = {
    "Steamworks.CSteamAPIContext": {"Init"},
    "Steamworks.SteamAPI": {"InitEx"},
    "Steamworks.SteamClient": {
        "GetISteamGenericInterface", "GetISteamGameSearch", "GetISteamMusicRemote", "GetISteamHTTP", "GetISteamUGC",
    },
}
IMPORTS = {
    "ISteamClient_GetISteamGenericInterface",
    "ISteamClient_GetISteamGameSearch",
    "ISteamClient_GetISteamMusicRemote",
    "ISteamClient_GetISteamHTTP",
    "ISteamClient_GetISteamUGC",
    "SteamInternal_SteamAPI_Init",
    "SteamInternal_CreateInterface",
    "SteamAPI_GetHSteamUser",
    "SteamAPI_GetHSteamPipe",
}


def inspect(path):
    content = path.read_bytes()
    pe = dnfile.dnPE(data=content)
    if pe.net is None or pe.net.mdtables.Assembly is None:
        raise ValueError("Not a managed assembly")
    tables = pe.net.mdtables
    names = {}
    selected = []
    for typedef in tables.TypeDef.rows:
        owner = "{}.{}".format(typedef.TypeNamespace, typedef.TypeName)
        for field in typedef.FieldList:
            names[0x04000000 | field.row_index] = owner + "." + str(field.row.Name)
        for method in typedef.MethodList:
            token = 0x06000000 | method.row_index
            names[token] = owner + "." + str(method.row.Name)
            if str(method.row.Name) in METHODS.get(owner, set()):
                selected.append((token, method.row))
    for index, row in enumerate(tables.MemberRef.rows, 1):
        owner = row.Class.row
        owner_name = str(getattr(owner, "TypeName", getattr(owner, "Name", "?")))
        namespace = str(getattr(owner, "TypeNamespace", ""))
        names[0x0A000000 | index] = namespace + "." + owner_name + "." + str(row.Name)

    def operand_value(operand):
        if operand is None or isinstance(operand, (int, float, str)):
            return operand
        if hasattr(operand, "value"):
            token = operand.value
            if token >> 24 == 0x70:
                return pe.net.user_strings.get(token & 0xFFFFFF).value
            return names.get(token, "0x{:08x}".format(token))
        return str(operand)

    assembly = tables.Assembly.rows[0]
    report = {
        "path": str(path),
        "sha256": hashlib.sha256(content).hexdigest(),
        "assembly_name": str(assembly.Name),
        "assembly_version": "{}.{}.{}.{}".format(
            assembly.MajorVersion, assembly.MinorVersion,
            assembly.BuildNumber, assembly.RevisionNumber,
        ),
        "clr_flags": pe.net.struct.Flags,
        "strong_name_signature_size": pe.net.struct.StrongNameSignatureSize,
        "methods": [],
        "native_imports": [],
        "scope": "Static inspection of this wrapper only; does not establish game call sites or native interface support.",
    }
    for token, row in selected:
        body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(row.Rva)))
        report["methods"].append({
            "name": names[token],
            "token": "0x{:08x}".format(token),
            "rva": row.Rva,
            "signature_hex": row.Signature.value.hex(),
            "code_size": body.code_size,
            "exception_handler_count": len(body.exception_handlers),
            "instructions": [{
                "method_body_offset": ins.offset,
                "opcode": ins.opcode.name,
                "operand": operand_value(ins.operand),
            } for ins in body.instructions],
        })
    for row in tables.ImplMap.rows:
        method = row.MemberForwarded.row
        if str(method.Name) not in IMPORTS:
            continue
        report["native_imports"].append({
            "method": str(method.Name),
            "entry_point": str(row.ImportName),
            "library": str(row.ImportScope.row.Name),
            "cdecl": bool(row.MappingFlags.pmCallConvCdecl),
            "signature_hex": method.Signature.value.hex(),
            "parameters": [str(param.row.Name) for param in method.ParamList],
        })
    pe.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembly", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.assembly), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
