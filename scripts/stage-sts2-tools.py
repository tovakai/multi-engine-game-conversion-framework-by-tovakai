"""Stage the converter's software allowlist for desktop application bundles."""

from pathlib import Path
import shutil
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
tools = root / "experiments/sts2-steamworks"
sys.path.insert(0, str(tools))
from package_converter import FILES

stage = Path(tempfile.mkdtemp(prefix="sts2-tools-"))
for name in FILES:
    target = stage / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tools / name, target)
shutil.copyfile(root / "LICENSE", stage / "LICENSE")
print(stage)
