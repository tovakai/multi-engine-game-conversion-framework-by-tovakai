import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest import mock
import zipfile

import adapt_deployment_graph as adaptation
import inspect_dependency_graph as inspection


class SyntheticDeploymentGraphTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "runtimeTarget": {"name": adaptation.SOURCE_TARGET, "signature": ""},
            "targets": {"base": {}, adaptation.SOURCE_TARGET: {
                adaptation.GAME: {"dependencies": {adaptation.SOURCE_DEPENDENCY: "9.0.7", "other": "1"},
                                  "runtime": {"game.dll": {}}},
                adaptation.SOURCE_PACK: {"runtime": {"System.dll": {"version": "9"}}, "native": {"coreclr.dll": {}}},
                "other/1": {"runtime": {"other.dll": {}}, "dependencies": {"another": "2"}}}},
            "libraries": {adaptation.SOURCE_PACK: {"type": "runtimepack"}, "other/1": {"path": "preserve"}},
            "runtimes": {"win-x64": ["win", "any", "base"]}, "extra": {"preserve": [1, 2, 3]}}
        self.raw = json.dumps(self.source).encode()
        self.expected = {}
        for mode, recipe in adaptation.MODES.items():
            value = copy.deepcopy(self.source)
            value["runtimeTarget"]["name"] = adaptation.TARGET
            old = value["targets"].pop(adaptation.SOURCE_TARGET)
            value["targets"][adaptation.TARGET] = {
                adaptation.GAME: {"dependencies": {adaptation.TARGET_DEPENDENCY: "9.0.7", "other": "1"},
                                  "runtime": {"game.dll": {}}},
                adaptation.TARGET_PACK: {"runtime": {"System.dll": {"version": "9"}},
                                         "native": {name: {} for name in adaptation.NATIVE_ASSETS}},
                "other/1": old["other/1"]}
            value["libraries"] = {adaptation.TARGET_PACK: {"type": "runtimepack"}, "other/1": {"path": "preserve"}}
            value["runtimes"] = {"linux-arm64": list(recipe["fallbacks"])}
            self.expected[mode] = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
        recipes = {mode: {"fallbacks": adaptation.MODES[mode]["fallbacks"],
                          "sha256": adaptation.digest(raw),
                          "semantic_sha256": adaptation.canonical_hash(json.loads(raw))}
                   for mode, raw in self.expected.items()}
        self.patches = [mock.patch.object(adaptation, "SOURCE_SHA256", adaptation.digest(self.raw)),
                        mock.patch.object(adaptation, "MODES", recipes)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_both_modes_match_independent_expected_graphs(self):
        for mode, expected in self.expected.items():
            raw = bytearray(self.raw)
            self.assertEqual(adaptation.adapt_deps(raw, mode=mode), expected)
            self.assertEqual(raw, self.raw)
            self.assertEqual(json.loads(expected)["extra"], self.source["extra"])

    def test_idempotence_and_cross_mode_refusal(self):
        for mode in self.expected:
            result = adaptation.adapt_deps(self.raw, mode=mode)
            self.assertEqual(adaptation.adapt_deps(result, mode=mode), result)
            other = "observed" if mode == "official-linux" else "official-linux"
            with self.assertRaisesRegex(ValueError, "mismatched"):
                adaptation.adapt_deps(result, mode=other)

    def test_unknown_input_mode_or_corrupted_output_refused(self):
        for raw, mode in ((self.raw + b" ", "observed"), (self.raw, "unknown"),
                          (self.expected["official-linux"] + b" ", "official-linux")):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                adaptation.adapt_deps(raw, mode=mode)

    def test_semantic_and_byte_output_pins_are_enforced(self):
        for field in ("semantic_sha256", "sha256"):
            recipe = {**adaptation.MODES["observed"], field: "0" * 64}
            with mock.patch.dict(adaptation.MODES, observed=recipe), self.assertRaisesRegex(ValueError, "verified recipe"):
                adaptation.adapt_deps(self.raw, mode="observed")

    def test_platform_mismatch_refused_even_with_mock_source_pin(self):
        value = copy.deepcopy(self.source)
        value["runtimes"] = {"win-x64": ["different"]}
        raw = json.dumps(value).encode()
        with mock.patch.object(adaptation, "SOURCE_SHA256", adaptation.digest(raw)):
            with self.assertRaisesRegex(ValueError, "platform"):
                adaptation.adapt_deps(raw, mode="observed")


class DeploymentEvidenceTests(unittest.TestCase):
    def test_official_runtime_provenance_and_deployed_hashes(self):
        root = Path(__file__).parent
        provenance = json.loads((root / "dotnet_runtime_907_provenance_v1.json").read_bytes())
        prototype = json.loads((root / "prototype_inventory_v1.json").read_bytes())
        records = {row["path"]: row for row in prototype["files"]}
        self.assertEqual(provenance["linux_arm64_fallbacks"], list(adaptation.LINUX_FALLBACKS))
        self.assertEqual(len(provenance["deployed_files"]), 186)
        for item in provenance["deployed_files"]:
            deployed = records[item["deployed_path"]]
            self.assertEqual(item["sha256"], deployed["sha256"])
            self.assertEqual(item["size_bytes"], deployed["size_bytes"])
        self.assertEqual(provenance["package"]["sha256"], "0b4f51690d4bb304c1a598848e025454c6689dfb19d9833291b9bb7255bfbd87")
        native = [row for row in provenance["deployed_files"] if "/native/" in row["package_path"]]
        self.assertEqual({row["package_path"].rsplit("/", 1)[1] for row in native}, set(adaptation.NATIVE_ASSETS))
        self.assertTrue(all(row["elf"] == {"class_bits": 64, "machine": 183} for row in native))


@unittest.skipUnless(os.environ.get("STS2_SOURCE_DEPS") and os.environ.get("STS2_PROTOTYPE_DEPS"),
                     "Set STS2_SOURCE_DEPS and STS2_PROTOTYPE_DEPS for local full captures")
class CapturedDeploymentGraphTests(unittest.TestCase):
    def setUp(self):
        self.source_raw = Path(os.environ["STS2_SOURCE_DEPS"]).read_bytes()
        self.prototype_raw = Path(os.environ["STS2_PROTOTYPE_DEPS"]).read_bytes()
        self.assertEqual(adaptation.digest(self.source_raw), inspection.SOURCE_SHA256)
        self.assertEqual(adaptation.digest(self.prototype_raw), "ae899ff7301d1506b22d3a229ea3b4cd240f4e9585b8b9268506a7154ff65870")
        self.source, self.prototype = json.loads(self.source_raw), json.loads(self.prototype_raw)

    def test_observed_replay_matches_entire_captured_graph(self):
        result = adaptation.adapt_deps(self.source_raw, mode="observed")
        self.assertEqual(json.loads(result), self.prototype)
        self.assertEqual(len(result), 34537)
        self.assertEqual(adaptation.digest(result), adaptation.MODES["observed"]["sha256"])
        self.assertNotEqual(result, self.prototype_raw)

    def test_official_candidate_differs_only_in_rid_fallbacks(self):
        result = adaptation.adapt_deps(self.source_raw, mode="official-linux")
        expected = copy.deepcopy(self.prototype)
        expected["runtimes"] = {"linux-arm64": list(adaptation.LINUX_FALLBACKS)}
        self.assertEqual(json.loads(result), expected)
        self.assertEqual(len(result), 34573)
        self.assertEqual(adaptation.digest(result), adaptation.MODES["official-linux"]["sha256"])

    def test_all_other_libraries_and_managed_records_preserved(self):
        result = json.loads(adaptation.adapt_deps(self.source_raw, mode="official-linux"))
        active = self.source["targets"][adaptation.SOURCE_TARGET]
        self.assertEqual(active[adaptation.SOURCE_PACK]["runtime"], result["targets"][adaptation.TARGET][adaptation.TARGET_PACK]["runtime"])
        for name in set(active) - {adaptation.GAME, adaptation.SOURCE_PACK}:
            self.assertEqual(active[name], result["targets"][adaptation.TARGET][name])
            self.assertEqual(self.source["libraries"][name], result["libraries"][name])
        old_game, new_game = copy.deepcopy(active[adaptation.GAME]), copy.deepcopy(result["targets"][adaptation.TARGET][adaptation.GAME])
        del old_game["dependencies"][adaptation.SOURCE_DEPENDENCY]
        del new_game["dependencies"][adaptation.TARGET_DEPENDENCY]
        self.assertEqual(old_game, new_game)

    def test_prototype_inspection_matches_archived_summary(self):
        root = Path(__file__).parent
        result = inspection.inspect(self.prototype_raw, adaptation.digest(self.prototype_raw))
        self.assertEqual(result, json.loads((root / "prototype_dependency_observation_v1.json").read_bytes()))

    @unittest.skipUnless(os.environ.get("STS2_DOTNET_RUNTIME_PACKAGE"), "Set STS2_DOTNET_RUNTIME_PACKAGE for official NuGet bytes")
    def test_official_package_framework_and_member_hashes(self):
        root = Path(__file__).parent
        provenance = json.loads((root / "dotnet_runtime_907_provenance_v1.json").read_bytes())
        path = Path(os.environ["STS2_DOTNET_RUNTIME_PACKAGE"])
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), provenance["package"]["sha256"])
        self.assertEqual(hashlib.sha512(raw).hexdigest(), provenance["package"]["sha512"])
        with zipfile.ZipFile(path) as archive:
            for item in provenance["deployed_files"]:
                self.assertEqual(hashlib.sha256(archive.read(item["package_path"])).hexdigest(), item["sha256"])
            framework = json.loads(archive.read("runtimes/linux-arm64/lib/net9.0/Microsoft.NETCore.App.deps.json"))
        self.assertEqual(framework["runtimes"]["linux-arm64"], list(adaptation.LINUX_FALLBACKS))
        official = next(iter(framework["targets"][adaptation.TARGET].values()))
        self.assertEqual(official["runtime"], self.prototype["targets"][adaptation.TARGET][adaptation.TARGET_PACK]["runtime"])


if __name__ == "__main__":
    unittest.main()
