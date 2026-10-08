import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import adapt_packed_manifests as adapter


class PackedManifestAdaptationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parent / "prototype_packed_extensions_v1.json"
        if not path.is_file():
            raise unittest.SkipTest("Local full-text device capture is not redistributed; synthetic coverage runs separately")
        report = json.loads(path.read_text())
        cls.packs = {pack["path"]: {item["path"]: item["text"].encode()
                                  for item in pack["extension_configs"]} for pack in report["packs"]}

    def test_both_manifest_edits_reproduce_exact_device_bytes(self):
        original = self.packs["SlayTheSpire2.pck.before-sentry-patch"]
        baseline = dict(original)
        result, report = adapter.adapt_bundle(original)
        self.assertEqual(result, self.packs["SlayTheSpire2.pck"])
        self.assertEqual(original, baseline)
        self.assertEqual([patch["size_delta_bytes"] for patch in report["patches"]], [204, 185])
        self.assertTrue(all(patch["applied"] and patch["verified"] for patch in report["patches"]))

    def test_partial_and_repeated_adaptation_are_idempotent(self):
        for name, resources in self.packs.items():
            with self.subTest(pack=name):
                result, report = adapter.adapt_bundle(resources)
                self.assertEqual(result, self.packs["SlayTheSpire2.pck"])
                repeated, repeated_report = adapter.adapt_bundle(result)
                self.assertEqual(repeated, result)
                self.assertTrue(all(not patch["applied"] for patch in repeated_report["patches"]))

    def test_unknown_second_manifest_cannot_change_first(self):
        resources = dict(self.packs["SlayTheSpire2.pck.before-sentry-patch"])
        resources["addons/sentry/sentry.gdextension"] += b"unknown modification"
        before = dict(resources)
        with self.assertRaisesRegex(ValueError, "Unknown manifest input hash"):
            adapter.adapt_bundle(resources)
        self.assertEqual(resources, before)

    def test_wrong_output_pin_is_refused(self):
        path = "addons/fmod/fmod.gdextension"
        source, target, edits = adapter.RECIPES[path]
        with mock.patch.dict(adapter.RECIPES, {path: (source, "0" * 64, edits)}):
            with self.assertRaisesRegex(ValueError, "output differs"):
                adapter.adapt_manifest(path, self.packs["SlayTheSpire2.pck.before-fmod-patch"][path])

    def test_unexpected_anchor_is_refused_even_with_known_input(self):
        path = "addons/fmod/fmod.gdextension"
        source, target, edits = adapter.RECIPES[path]
        with mock.patch.dict(adapter.RECIPES, {path: (source, target, ((b"missing anchor", b"replacement"),))}):
            with self.assertRaisesRegex(ValueError, "anchor"):
                adapter.adapt_manifest(path, self.packs["SlayTheSpire2.pck.before-fmod-patch"][path])

    def test_missing_or_modified_preserved_configs_are_refused(self):
        for path in adapter.UNCHANGED:
            resources = dict(self.packs["SlayTheSpire2.pck"])
            del resources[path]
            with self.assertRaisesRegex(ValueError, "Missing verified"):
                adapter.adapt_bundle(resources)
            resources[path] = b"unknown content"
            with self.assertRaisesRegex(ValueError, "unchanged resource hash"):
                adapter.adapt_bundle(resources)

    def test_unknown_recipe_path_is_refused_and_extra_assets_preserved(self):
        with self.assertRaisesRegex(ValueError, "No verified"):
            adapter.adapt_manifest("unknown.gdextension", b"any content")
        resources = dict(self.packs["SlayTheSpire2.pck"])
        resources["assets/synthetic.bin"] = b"unchanged asset"
        result, _ = adapter.adapt_bundle(resources)
        self.assertEqual(result["assets/synthetic.bin"], b"unchanged asset")

    def test_archived_device_config_text_hashes_and_metadata_scope(self):
        report = json.loads((Path(__file__).parent / "prototype_packed_extensions_v1.json").read_text())
        self.assertEqual(report["errors"], [])
        self.assertEqual([item["changed_metadata_count"] for item in report["comparisons"]], [1, 2])
        for pack in report["packs"]:
            self.assertEqual(pack["entry_count"], 13158)
            for item in pack["extension_configs"]:
                self.assertTrue(item["table_md5_matches"])
                self.assertEqual(hashlib.sha256(item["text"].encode()).hexdigest(), item["sha256"])


class SyntheticPackedManifestTests(PackedManifestAdaptationTests):
    @classmethod
    def setUpClass(cls):
        fmod = "addons/fmod/fmod.gdextension"
        sentry = "addons/sentry/sentry.gdextension"
        cls.real_recipes = dict(adapter.RECIPES)
        prefix = b'[configuration]\nentry_symbol = "fmod_library_init"\n\n[libraries]\n\n'
        icons = b'[icons]\nSyntheticIcon = "synthetic.svg"\n\n'
        fmod_source = prefix + icons + b'[dependencies]\n'
        fmod_target = (prefix + b'linux.release.arm64 = "res://addons/fmod/libs/linux/libGodotFmod.linux.template_release.arm64.so"\n\n'
                       + icons + b'[dependencies]\n\nlinux.release.arm64 = {\n    "libs/linux/libfmod.so.14": "",\n    "libs/linux/libfmodstudio.so.14": ""\n}\n\n')
        sentry_source = b'[configuration]\nentry_symbol = "gdextension_init"\n\n[libraries]\n\n[dependencies]\n\n'
        sentry_target = (b'[configuration]\nentry_symbol = "sentry_gdextension_init"\n\n[libraries]\n\n'
                         + b'linux.release.arm64 = "res://addons/sentry/bin/linux/arm64/libsentry.linux.release.arm64.so"\n\n'
                         + b'[dependencies]\n\nlinux.arm64 = {\n    "res://addons/sentry/bin/linux/arm64/crashpad_handler" : ""\n}\n\n\n')
        preserved = {
            ".godot/extension_list.cfg": b"res://synthetic/extension.gdextension\n",
            "bin/spine_godot_extension.gdextension": b'[configuration]\nentry_symbol = "synthetic_spine_init"\n',
        }
        cls.packs = {
            "SlayTheSpire2.pck.before-sentry-patch": {**preserved, fmod: fmod_source, sentry: sentry_source},
            "SlayTheSpire2.pck.before-fmod-patch": {**preserved, fmod: fmod_source, sentry: sentry_target},
            "SlayTheSpire2.pck": {**preserved, fmod: fmod_target, sentry: sentry_target},
        }
        recipes = {name: (adapter.digest(before), adapter.digest(after), adapter.RECIPES[name][2])
                   for name, before, after in ((fmod, fmod_source, fmod_target), (sentry, sentry_source, sentry_target))}
        for patcher in (mock.patch.dict(adapter.RECIPES, recipes),
                        mock.patch.dict(adapter.UNCHANGED, {name: adapter.digest(raw) for name, raw in preserved.items()})):
            patcher.start()
            cls.addClassCleanup(patcher.stop)

    def test_archived_device_config_text_hashes_and_metadata_scope(self):
        report = json.loads((Path(__file__).parent / "prototype_packed_extension_hashes_v1.json").read_text())
        self.assertEqual(report["errors"], [])
        packs = {item["path"]: {resource["path"]: resource for resource in item["extension_configs"]}
                 for item in report["packs"]}
        for name, (source, target, _) in self.real_recipes.items():
            self.assertEqual(packs["SlayTheSpire2.pck.before-sentry-patch"][name]["sha256"], source)
            self.assertEqual(packs["SlayTheSpire2.pck"][name]["sha256"], target)
        self.assertEqual([item["changed_metadata_count"] for item in report["comparisons"]], [1, 2])
        for pack in report["packs"]:
            for item in pack["extension_configs"]:
                self.assertNotIn("text", item)
                self.assertTrue(item["table_md5_matches"])


if __name__ == "__main__":
    unittest.main()
