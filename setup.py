"""Embed provenance in wheels and source distributions without editing the checkout."""
import json
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist


def stamp(destination):
    from megcfbt.version import packaged_build_info
    path = Path(destination) / "megcfbt" / "_build_info.json"
    path.write_text(json.dumps(packaged_build_info(), indent=2) + "\n", encoding="utf-8")


class BuildPy(build_py):
    def run(self):
        super().run()
        stamp(self.build_lib)


class Sdist(sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        stamp(base_dir)


setup(cmdclass={"build_py": BuildPy, "sdist": Sdist})
