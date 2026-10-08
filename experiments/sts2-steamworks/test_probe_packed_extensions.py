import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import probe_packed_extensions as probe


def make_pack(files, version=3, base=128, directory=2048, pack_flags=2, entry_flags=0):
    payload = bytearray(max(directory + 4, base + sum(len(data) for _, data in files)))
    struct.pack_into("<6IQ", payload, 0, 0x43504447, version, 4, 5, 1, pack_flags, base)
    if version == 3:
        struct.pack_into("<Q", payload, 32, directory)
    else:
        directory = 96
    table = bytearray(struct.pack("<I", len(files)))
    offset = 0
    for name, data in files:
        encoded = name.encode()
        encoded += b"\0" * (-len(encoded) % 4)
        table.extend(struct.pack("<I", len(encoded)) + encoded)
        table.extend(struct.pack("<QQ16sI", offset, len(data), hashlib.md5(data).digest(), entry_flags))
        payload[base + offset:base + offset + len(data)] = data
        offset += len(data)
    payload[directory:directory + len(table)] = table
    return bytes(payload)


class PackedExtensionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def add(self, name, content):
        path = self.root / name
        path.write_bytes(content)
        return path

    def test_v2_and_v3_offsets_selected_configs_and_no_writes(self):
        files = [("res://addons/fmod/fmod.gdextension", b'[configuration]\nentry_symbol="fmod_library_init"\n'),
                 ("res://.godot/extension_list.cfg", b"res://addons/fmod/fmod.gdextension\n"),
                 ("res://assets/card.bin", b"unselected payload")]
        for version, base in ((2, 1024), (3, 128)):
            raw = make_pack(files, version=version, base=base)
            path = self.add("pack.pck", raw)
            report, table = probe.inspect_pack(path, len(raw))
            self.assertEqual(report["format"], version)
            self.assertEqual(report["godot_version"], [4, 5, 1])
            self.assertEqual(report["entry_count"], 3)
            self.assertEqual(len(report["extension_configs"]), 2)
            self.assertTrue(all(item["table_md5_matches"] for item in report["extension_configs"]))
            self.assertEqual(table["assets/card.bin"]["size_bytes"], len(files[2][1]))
            self.assertNotIn("unselected payload", json.dumps(report))
            self.assertEqual(path.read_bytes(), raw)

    def test_metadata_comparison_does_not_treat_relocation_as_content_change(self):
        files = [("a.gdextension", b"original"), ("asset.bin", b"unchanged")]
        previous = make_pack(files, base=128)
        current = make_pack([(files[0][0], b"updated!"), files[1]], base=256)
        self.add("SlayTheSpire2.pck", current)
        self.add("previous", previous)
        result = probe.collect(self.root, {"SlayTheSpire2.pck": len(current), "previous": len(previous)})
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["comparisons"][0]["changed_paths"], ["a.gdextension"])

    def test_encrypted_sparse_unknown_format_and_flags_are_refused(self):
        for flags in (1, 4, 8):
            with self.subTest(flags=flags):
                with self.assertRaisesRegex(ValueError, "PCK flags"):
                    probe.inspect_pack(self.add("pack", make_pack([], pack_flags=flags)))
        for flags in (1, 4):
            with self.assertRaisesRegex(ValueError, "resource flags"):
                probe.inspect_pack(self.add("pack", make_pack([("a", b"x")], entry_flags=flags)))
        with self.assertRaisesRegex(ValueError, "format"):
            probe.inspect_pack(self.add("pack", make_pack([], version=4)))

    def test_removed_resources_are_not_read_as_configs(self):
        path = self.add("pack", make_pack([("removed.gdextension", b"ignore")], entry_flags=2))
        report, table = probe.inspect_pack(path)
        self.assertEqual(report["extension_configs"], [])
        self.assertEqual(table["removed.gdextension"]["flags"], 2)

    def test_size_symlink_and_duplicate_path_guards(self):
        raw = make_pack([("a", b"one"), ("res://a", b"two")])
        path = self.add("pack", raw)
        with self.assertRaisesRegex(ValueError, "size differs"):
            probe.inspect_pack(path, len(raw) + 1)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            probe.inspect_pack(path)
        link = self.root / "link"
        link.symlink_to(path)
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            probe.inspect_pack(link)

    def test_truncation_directory_path_count_and_resource_bounds(self):
        raw = make_pack([("a", b"payload")])
        for offset, layout, value in ((32, "<Q", len(raw) + 1), (2048, "<I", 200001),
                                      (2052, "<I", 4097), (2068, "<Q", len(raw) + 1)):
            candidate = bytearray(raw)
            struct.pack_into(layout, candidate, offset, value)
            with self.subTest(offset=offset):
                with self.assertRaises(ValueError):
                    probe.inspect_pack(self.add("pack", candidate))
        with self.assertRaisesRegex(ValueError, "truncated"):
            probe.inspect_pack(self.add("pack", raw[:12]))

    def test_config_size_limit_and_actual_md5_mismatch_reporting(self):
        with self.assertRaisesRegex(ValueError, "configuration inspection limit"):
            probe.inspect_pack(self.add("pack", make_pack([("a.gdextension", b"x" * 65537)], directory=70000)))
        raw = bytearray(make_pack([("a.gdextension", b"manifest")]))
        raw[128] = ord("M")
        report, _ = probe.inspect_pack(self.add("pack", raw))
        config = report["extension_configs"][0]
        self.assertFalse(config["table_md5_matches"])
        self.assertEqual(config["sha256"], hashlib.sha256(b"Manifest").hexdigest())

    def test_changed_file_refusal_and_error_json(self):
        path = self.add("pack", make_pack([]))
        with mock.patch.object(probe, "stamp", side_effect=[1, 2]):
            with self.assertRaisesRegex(ValueError, "changed"):
                probe.inspect_pack(path)
        report = probe.collect(self.root, {"missing": 1})
        self.assertEqual(report["packs"], [])
        self.assertEqual(len(report["errors"]), 1)

    def test_published_heredoc_is_the_complete_tested_probe(self):
        directory = Path(__file__).parent
        document = (directory / "FRAME_PACKED_EXTENSIONS.md").read_text()
        code = (directory / "probe_packed_extensions.py").read_text()
        self.assertEqual(document.count("```bash"), 1)
        self.assertIn("python3 - <<'PY'\n" + code + "PY\n```", document)


if __name__ == "__main__":
    unittest.main()
