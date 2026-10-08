import hashlib
import json
import os
from pathlib import Path
import struct
import unittest
import zipfile


class GodotRuntimeProvenanceTests(unittest.TestCase):
    def test_archive_engine_pin_matches_prototype_record(self):
        root = Path(__file__).parent
        provenance = json.loads((root / "godot_mono_451_provenance_v1.json").read_bytes())
        inventory = json.loads((root / "prototype_inventory_v1.json").read_bytes())
        engine = provenance["engine"]
        row = next(f for f in inventory["files"] if f["path"] == engine["deployed_path"])
        self.assertEqual(engine["size_bytes"], row["size_bytes"])
        self.assertEqual(engine["sha256"], row["sha256"])
        self.assertEqual(engine["elf"], row["elf"])
        self.assertEqual(engine["member"], "templates/linux_release.arm64")
        self.assertEqual(provenance["archive"]["version"], "4.5.1.stable.mono")

    @unittest.skipUnless(os.environ.get("STS2_GODOT_MONO_TEMPLATES"), "Set STS2_GODOT_MONO_TEMPLATES for the official archive")
    def test_full_download_checksum_and_member_match_record(self):
        root = Path(__file__).parent
        provenance = json.loads((root / "godot_mono_451_provenance_v1.json").read_bytes())
        path = Path(os.environ["STS2_GODOT_MONO_TEMPLATES"])
        sha512, sha256 = hashlib.sha512(), hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1048576), b""):
                sha512.update(block)
                sha256.update(block)
        self.assertEqual(path.stat().st_size, provenance["archive"]["size_bytes"])
        self.assertEqual(sha512.hexdigest(), provenance["archive"]["sha512"])
        self.assertEqual(sha256.hexdigest(), provenance["archive"]["sha256"])
        with zipfile.ZipFile(path) as archive:
            raw = archive.read(provenance["engine"]["member"])
            self.assertEqual(archive.read("templates/version.txt").decode().strip(), provenance["archive"]["version"])
        self.assertEqual(len(raw), provenance["engine"]["size_bytes"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), provenance["engine"]["sha256"])
        self.assertEqual(raw[:6], b"\x7fELF\x02\x01")
        self.assertEqual(struct.unpack_from("<H", raw, 18)[0], 183)


class SentryRuntimeProvenanceTests(unittest.TestCase):
    def test_selected_members_match_prototype_and_manifest_is_separate(self):
        root = Path(__file__).parent
        provenance = json.loads((root / "sentry_godot_150_provenance_v1.json").read_bytes())
        inventory = json.loads((root / "prototype_inventory_v1.json").read_bytes())
        records = {row["path"]: row for row in inventory["files"]}
        for item in provenance["deployed_files"]:
            row = records[item["deployed_path"]]
            self.assertEqual(item["sha256"], row["sha256"])
            self.assertEqual(item["size_bytes"], row["size_bytes"])
            self.assertEqual(item["elf"], row["elf"])
        self.assertEqual(provenance["source"]["commit"], "6c4d74ece1fab5eb841fc7c7135341a4abb28497")
        self.assertEqual(provenance["official_manifest"]["size_bytes"], 3891)
        self.assertNotEqual(provenance["official_manifest"]["sha256"],
                            "afeceb8ec9095aaac5f1ed57c2d79f152844de1bd78fd57442a0687d3da726bc")

    @unittest.skipUnless(os.environ.get("STS2_SENTRY_ARCHIVE"), "Set STS2_SENTRY_ARCHIVE for the official asset")
    def test_full_archive_and_selected_elf_members(self):
        from io import BytesIO
        from elftools.elf.elffile import ELFFile

        root = Path(__file__).parent
        provenance = json.loads((root / "sentry_godot_150_provenance_v1.json").read_bytes())
        path = Path(os.environ["STS2_SENTRY_ARCHIVE"])
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1048576), b""):
                digest.update(block)
        self.assertEqual(path.stat().st_size, provenance["archive"]["size_bytes"])
        self.assertEqual(digest.hexdigest(), provenance["archive"]["sha256"])
        with zipfile.ZipFile(path) as archive:
            for item in provenance["deployed_files"]:
                raw = archive.read(item["member"])
                self.assertEqual(len(raw), item["size_bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])
                self.assertEqual(raw[:6], b"\x7fELF\x02\x01")
                self.assertEqual(struct.unpack_from("<H", raw, 18)[0], 183)
                if "defined_export_verified" in item:
                    elf = ELFFile(BytesIO(raw))
                    defined = {symbol.name for symbol in elf.get_section_by_name(".dynsym").iter_symbols()
                               if symbol["st_shndx"] != "SHN_UNDEF"}
                    self.assertIn(item["defined_export_verified"], defined)
            manifest = archive.read(provenance["official_manifest"]["member"])
        self.assertEqual(len(manifest), provenance["official_manifest"]["size_bytes"])
        self.assertEqual(hashlib.sha256(manifest).hexdigest(), provenance["official_manifest"]["sha256"])


if __name__ == "__main__":
    unittest.main()
