#!/usr/bin/env python3
"""Decode actual game stats IL and native ARM64 stats thunks without execution."""

import argparse
import hashlib
import json
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBytes
from elftools.elf.elffile import ELFFile


def inspect_game(path):
    content = path.read_bytes()
    pe = dnfile.dnPE(data=content)
    tables = pe.net.mdtables
    nested = {row.NestedClass.row_index: row.EnclosingClass.row_index for row in tables.NestedClass.rows}
    def owner(index):
        row = tables.TypeDef.rows[index - 1]
        return owner(nested[index]) + "+" + str(row.TypeName) if index in nested else str(row.TypeNamespace) + "." + str(row.TypeName)
    names, selected_types = {}, []
    for index, row in enumerate(tables.TypeDef.rows, 1):
        name = owner(index)
        if "SteamStatsManager" in name or name in {
            "MegaCrit.Sts2.Core.Platform.StatsManager", "MegaCrit.Sts2.Core.Platform.AchievementsUtil",
            "MegaCrit.Sts2.Core.Platform.Null.NullAchievementStrategy",
        }:
            selected_types.append({"name": name, "fields": [
                {"token": hex(0x04000000 | field.row_index), "name": str(field.row.Name),
                 "signature_hex": field.row.Signature.value.hex()} for field in row.FieldList]})
        for field in row.FieldList:
            names[0x04000000 | field.row_index] = name + "." + str(field.row.Name)
        for method in row.MethodList:
            names[0x06000000 | method.row_index] = name + "." + str(method.row.Name)
    def reference_owner(index):
        row = index.row
        if index.table.name == "TypeDef":
            return owner(index.row_index)
        if index.table.name == "TypeRef":
            return str(row.TypeNamespace) + "." + str(row.TypeName)
        if index.table.name == "TypeSpec":
            return "TypeSpec(signature=" + row.Signature.value.hex() + ")"
        return str(getattr(row, "Name", "?"))
    for index, row in enumerate(tables.MemberRef.rows, 1):
        names[0x0A000000 | index] = reference_owner(row.Class) + "." + str(row.Name)
    for index, row in enumerate(tables.MethodSpec.rows, 1):
        tag = 0x06000000 if row.Method.table.name == "MethodDef" else 0x0A000000
        names[0x2B000000 | index] = names[tag | row.Method.row_index] + "(instantiation=" + row.Instantiation.value.hex() + ")"
    watched = {token for token, name in names.items() if "SteamStatsManager" in name or "SteamUserStats" in name}
    report = {
        "path": str(path), "sha256": hashlib.sha256(content).hexdigest(),
        "clr_flags": pe.net.struct.Flags,
        "strong_name_signature_size": pe.net.struct.StrongNameSignatureSize,
        "managed_native_header_size": pe.net.struct.ManagedNativeHeaderSize,
        "method_bodies_decoded": 0, "errors": [], "types": selected_types,
        "methods": [], "references": [],
    }
    selected = tuple(item["name"] for item in selected_types)
    for index, row in enumerate(tables.MethodDef.rows, 1):
        if not row.Rva:
            continue
        name = names[0x06000000 | index]
        try:
            # The largest method in this supplied assembly is below this bound.
            body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(row.Rva, 1024 * 1024)))
        except Exception as error:
            report["errors"].append({"method": name, "error": str(error)})
            continue
        report["method_bodies_decoded"] += 1
        refs, instructions = [], []
        for ins in body.instructions:
            token = getattr(ins.operand, "value", None)
            if token in watched:
                refs.append({"offset": ins.offset - body.header_size, "opcode": ins.opcode.name,
                             "target": names[token], "token": hex(token)})
            operand = names.get(token, str(ins.operand))
            if ins.opcode.name == "ldstr":
                operand = pe.net.user_strings.get(token & 0xFFFFFF).value
            instructions.append({"offset": ins.offset - body.header_size, "opcode": ins.opcode.name,
                                 "operand": operand, "token": hex(token) if token is not None else None})
        if refs:
            report["references"].append({"method": name, "references": refs})
        if any(name.startswith(value + ".") for value in selected) or "NGame+<GameStartup>" in name:
            report["methods"].append({"name": name, "token": hex(0x06000000 | index),
                "rva": row.Rva, "file_offset": pe.get_offset_from_rva(row.Rva),
                "signature_hex": row.Signature.value.hex(), "header_hex": body.get_header_bytes().hex(),
                "code_size": body.code_size, "max_stack": body.max_stack,
                "local_signature_token": hex(body.local_var_sig_tok.value) if body.local_var_sig_tok else None,
                "exception_handler_count": len(body.exception_handlers), "instructions": instructions})
    pe.close()
    return report


def inspect_native(path):
    report = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "exports": []}
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf["e_machine"] != "EM_AARCH64":
            raise ValueError("Native inspection requires an AArch64 ELF")
        dis = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
        text = elf.get_section_by_name(".text")
        content = text.data()
        for symbol in elf.get_section_by_name(".dynsym").iter_symbols():
            if not symbol.name.startswith("SteamAPI_ISteamUserStats_") or symbol["st_shndx"] == "SHN_UNDEF":
                continue
            offset = symbol["st_value"] - text["sh_addr"]
            code = content[offset:offset + symbol["st_size"]]
            instructions = [{"address": ins.address, "mnemonic": ins.mnemonic, "operands": ins.op_str}
                            for ins in dis.disasm(code, symbol["st_value"])]
            if len(instructions) * 4 != len(code):
                raise ValueError("Incomplete native disassembly for " + symbol.name)
            report["exports"].append({"name": symbol.name, "instructions": instructions})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path)
    parser.add_argument("native", type=Path)
    args = parser.parse_args()
    report = {"scope": "Static IL and ELF inspection only; no game or Steam execution.",
              "game": inspect_game(args.game), "native": inspect_native(args.native)}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["game"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
