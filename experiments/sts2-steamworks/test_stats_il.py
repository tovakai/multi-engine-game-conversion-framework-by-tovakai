"""Static evidence checks against the supplied assemblies and ARM64 library."""

import os
from pathlib import Path
import unittest

import patch_accessors
import patch_stats

try:
    import dnfile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBytes
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
    from elftools.elf.elffile import ELFFile
    INSPECTION_AVAILABLE = True
except ImportError:
    INSPECTION_AVAILABLE = False

FIXTURES = tuple(os.environ.get(name) for name in ("STS2_WRAPPER_DLL", "STS2_GAME_DLL", "STS2_NATIVE_LIBRARY"))
# Slot order from Valve's SDK 1.63 ISteamUserStats (interface 013), vendored in Proton.
NATIVE_METHODS = (
    "GetStatInt32", "GetStatFloat", "SetStatInt32", "SetStatFloat", "UpdateAvgRateStat",
    "GetAchievement", "SetAchievement", "ClearAchievement", "GetAchievementAndUnlockTime",
    "StoreStats", "GetAchievementIcon", "GetAchievementDisplayAttribute", "IndicateAchievementProgress",
    "GetNumAchievements", "GetAchievementName", "RequestUserStats", "GetUserStatInt32",
    "GetUserStatFloat", "GetUserAchievement", "GetUserAchievementAndUnlockTime", "ResetAllStats",
    "FindOrCreateLeaderboard", "FindLeaderboard", "GetLeaderboardName", "GetLeaderboardEntryCount",
    "GetLeaderboardSortMethod", "GetLeaderboardDisplayType", "DownloadLeaderboardEntries",
    "DownloadLeaderboardEntriesForUsers", "GetDownloadedLeaderboardEntry", "UploadLeaderboardScore",
    "AttachLeaderboardUGC", "GetNumberOfCurrentPlayers", "RequestGlobalAchievementPercentages",
    "GetMostAchievedAchievementInfo", "GetNextMostAchievedAchievementInfo", "GetAchievementAchievedPercent",
    "RequestGlobalStats", "GetGlobalStatInt64", "GetGlobalStatDouble", "GetGlobalStatHistoryInt64",
    "GetGlobalStatHistoryDouble", "GetAchievementProgressLimitsInt32", "GetAchievementProgressLimitsFloat",
)


@unittest.skipUnless(all(FIXTURES) and INSPECTION_AVAILABLE, "Requires the inspection dependencies and all three fixtures")
class StatsILTests(unittest.TestCase):
    def test_game_changes_one_method_and_preserves_all_other_bodies(self):
        original = Path(FIXTURES[1]).read_bytes()
        candidate = patch_stats.patched_bytes(original, patch_stats.RECIPES[1])
        source, target = dnfile.dnPE(data=original), dnfile.dnPE(data=candidate)
        self.addCleanup(source.close)
        self.addCleanup(target.close)
        self.assertEqual(source.net.struct.dump(), target.net.struct.dump())
        self.assertEqual(source.net.struct.StrongNameSignatureSize, 0)
        self.assertEqual(source.net.struct.ManagedNativeHeaderSize, 0)
        count, changed, obsolete_calls = 0, [], []
        for index, method in enumerate(source.net.mdtables.MethodDef.rows, 1):
            if not method.Rva:
                continue
            before = CilMethodBody(CilMethodBodyReaderBytes(source.get_data(method.Rva, 1024 * 1024)))
            after = CilMethodBody(CilMethodBodyReaderBytes(target.get_data(method.Rva, 1024 * 1024)))
            count += 1
            if before.raw_bytes != after.raw_bytes:
                changed.append(index)
            for ins in before.instructions:
                if ins.opcode.name == "call" and ins.operand.value == 0x0a001131:
                    obsolete_calls.append(index)
        self.assertEqual(count, 46701)
        self.assertEqual(changed, [3964])
        self.assertEqual(obsolete_calls, [3964])
        body = CilMethodBody(CilMethodBodyReaderBytes(patch_stats.GAME_AFTER))
        self.assertEqual(body.code_size, 82)
        self.assertEqual(body.max_stack, 2)
        self.assertEqual(body.local_var_sig_tok.value, 0x11000004)
        self.assertEqual(target.net.mdtables.StandAloneSig.rows[3].Signature.value, b"\x07\x01\x08")
        self.assertEqual(body.exception_handlers, [])
        self.assertEqual(body.instructions[-1].opcode.name, "ret")
        self.assertNotIn(0x0a001131, [getattr(ins.operand, "value", None) for ins in body.instructions])
        self.assertIn(0x0a001132, [getattr(ins.operand, "value", None) for ins in body.instructions])
        self.assertIn(0x06000f80, [getattr(ins.operand, "value", None) for ins in body.instructions])

    def test_wrapper_changes_only_the_stats_factory_string(self):
        original = patch_accessors.patched_bytes(Path(FIXTURES[0]).read_bytes())
        original = patch_accessors.patched_bytes(original, "client023-v2")
        candidate = patch_stats.patched_bytes(original, patch_stats.RECIPES[0])
        self.assertEqual([(i, a, b) for i, (a, b) in enumerate(zip(original, candidate)) if a != b], [(360744, 50, 51)])
        pe = dnfile.dnPE(data=candidate)
        self.addCleanup(pe.close)
        self.assertEqual(pe.net.user_strings.get(0x7cf).value, "STEAMUSERSTATS_INTERFACE_VERSION013")
        self.assertEqual(pe.net.user_strings.get(0x6fd).value, "SteamClient023")

    def test_all_native_stats_thunks_match_interface_013(self):
        with Path(FIXTURES[2]).open("rb") as stream:
            elf = ELFFile(stream)
            self.assertEqual(elf["e_machine"], "EM_AARCH64")
            text = elf.get_section_by_name(".text")
            data = text.data()
            dis = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
            dis.detail = True
            matched = set()
            for symbol in elf.get_section_by_name(".dynsym").iter_symbols():
                if not symbol.name.startswith("SteamAPI_ISteamUserStats_"):
                    continue
                name = symbol.name.removeprefix("SteamAPI_ISteamUserStats_")
                offset = symbol["st_value"] - text["sh_addr"]
                ins = list(dis.disasm(data[offset:offset + symbol["st_size"]], symbol["st_value"]))
                self.assertEqual([i.mnemonic for i in ins], ["ldr", "ldr", "mov", "br"])
                self.assertEqual(ins[1].operands[1].mem.disp, NATIVE_METHODS.index(name) * 8)
                matched.add(name)
            self.assertEqual(matched, set(NATIVE_METHODS))


if __name__ == "__main__":
    unittest.main()
