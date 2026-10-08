import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import adapt_fmod_build_sources as adapter


class SyntheticFmodSourceTests(unittest.TestCase):
    def setUp(self):
        self.sources = {"SConstruct": b"# synthetic\n" + adapter.RECIPES["SConstruct"][2],
                        "src/helpers/common.h": adapter.RECIPES["src/helpers/common.h"][2] + b"// synthetic\n"}
        self.outputs = {name: raw.replace(adapter.RECIPES[name][2], adapter.RECIPES[name][3]) for name, raw in self.sources.items()}
        pins = {name: (adapter.digest(raw), adapter.digest(self.outputs[name]), *adapter.RECIPES[name][2:]) for name, raw in self.sources.items()}
        patcher = mock.patch.dict(adapter.RECIPES, pins)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_forward_reverse_idempotent_no_mutation_and_extra_files_preserved(self):
        resources = {**self.sources, "asset.bin": b"preserved"}
        baseline = dict(resources)
        patched, report = adapter.adapt_sources(resources)
        self.assertEqual(resources, baseline)
        self.assertEqual(patched, {**self.outputs, "asset.bin": b"preserved"})
        self.assertEqual([row["size_delta_bytes"] for row in report["patches"]], [35, 18])
        repeated, report = adapter.adapt_sources(patched)
        self.assertEqual(repeated, patched)
        self.assertTrue(all(not row["applied"] for row in report["patches"]))
        restored, _ = adapter.adapt_sources(patched, restore=True)
        self.assertEqual(restored, resources)
        restored, report = adapter.adapt_sources(restored, restore=True)
        self.assertTrue(all(not row["applied"] for row in report["patches"]))

    def test_unknown_mixed_and_missing_inputs_refused(self):
        for resources in ({**self.sources, "src/helpers/common.h": b"unknown"},
                          {**self.sources, "src/helpers/common.h": self.outputs["src/helpers/common.h"]}):
            baseline = dict(resources)
            for restore in (False, True):
                with self.assertRaisesRegex(ValueError, "Unknown or mixed"):
                    adapter.adapt_sources(resources, restore=restore)
            self.assertEqual(resources, baseline)
        with self.assertRaisesRegex(ValueError, "Missing"):
            adapter.adapt_sources({"SConstruct": self.sources["SConstruct"]})

    def test_wrong_output_pin_refuses_entire_result(self):
        name = "src/helpers/common.h"
        source, _, before, after = adapter.RECIPES[name]
        with mock.patch.dict(adapter.RECIPES, {name: (source, "0" * 64, before, after)}):
            with self.assertRaisesRegex(ValueError, "output differs"):
                adapter.adapt_sources(self.sources)

    def test_missing_or_duplicate_anchor_refused_even_with_input_pin(self):
        name = "SConstruct"
        source, target, before, after = adapter.RECIPES[name]
        with mock.patch.dict(adapter.RECIPES, {name: (source, target, b"absent", after)}):
            with self.assertRaisesRegex(ValueError, "anchor"):
                adapter.adapt_sources(self.sources)
        duplicate = {**self.sources, name: self.sources[name] + before}
        with mock.patch.dict(adapter.RECIPES, {name: (adapter.digest(duplicate[name]), target, before, after)}):
            with self.assertRaisesRegex(ValueError, "anchor"):
                adapter.adapt_sources(duplicate)

    def test_reverse_anchor_refused_and_outputs_are_not_partially_exposed(self):
        name = "src/helpers/common.h"
        source, target, before, _ = adapter.RECIPES[name]
        with mock.patch.dict(adapter.RECIPES, {name: (source, target, before, b"absent")}):
            with self.assertRaisesRegex(ValueError, "anchor"):
                adapter.adapt_sources(self.outputs, restore=True)


class ObservedFmodSourceTests(unittest.TestCase):
    def test_observed_hashes_and_diffs_bind_exact_recipe(self):
        observation = json.loads((Path(__file__).parent / "fmod_source_observation_v1.json").read_text())
        self.assertEqual(observation["errors"], [])
        self.assertEqual(observation["commit"], adapter.SOURCE_COMMIT)
        for row in observation["files"]:
            source, target, before, after = adapter.RECIPES[row["path"]]
            self.assertEqual((row["base_sha256"], row["current_sha256"]), (source, target))
            self.assertEqual(row["current_size_bytes"] - row["base_size_bytes"], len(after) - len(before))
            self.assertFalse(row["diff_truncated"])
            self.assertEqual(hashlib.sha256(row["diff"].encode()).hexdigest(), row["diff_sha256"])

    @unittest.skipUnless(os.environ.get("STS2_FMOD_SCONSTRUCT") and os.environ.get("STS2_FMOD_COMMON_HEADER"), "Pinned upstream source files not supplied")
    def test_full_upstream_files_replay_and_restore_exact_device_hashes(self):
        sources = {"SConstruct": Path(os.environ["STS2_FMOD_SCONSTRUCT"]).read_bytes(),
                   "src/helpers/common.h": Path(os.environ["STS2_FMOD_COMMON_HEADER"]).read_bytes()}
        baseline = dict(sources)
        outputs, report = adapter.adapt_sources(sources)
        self.assertEqual(sources, baseline)
        restored, _ = adapter.adapt_sources(outputs, restore=True)
        self.assertEqual(restored, sources)
        self.assertEqual(outputs["src/helpers/common.h"], b"#include <cstdio>\n" + sources["src/helpers/common.h"])
        original = ast.parse(sources["SConstruct"])
        call = ast.parse('env.Append(LINKFLAGS=["-m64", "-fuse-ld=gold"])').body[0]
        class Guard(ast.NodeTransformer):
            def visit_Expr(self, node):
                if ast.dump(node) == ast.dump(call):
                    replacement = ast.parse('if env["arch"] != "arm64":\n    pass').body[0]
                    replacement.body = [copy.deepcopy(node)]
                    return replacement
                return node
        expected = Guard().visit(original)
        self.assertEqual(ast.dump(expected), ast.dump(ast.parse(outputs["SConstruct"])))
        self.assertEqual([row["size_delta_bytes"] for row in report["patches"]], [35, 18])


if __name__ == "__main__":
    unittest.main()
