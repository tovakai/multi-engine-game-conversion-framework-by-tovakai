"""Compare generated package bytes/permissions, ignoring ZIP timestamps."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def content_index(path):
    result = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            digest = hashlib.sha256()
            with archive.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            result[info.filename] = (digest.hexdigest(), info.external_attr >> 16 & 0o777)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    left, right = content_index(args.left), content_index(args.right)
    differences = sorted(name for name in left.keys() | right.keys() if left.get(name) != right.get(name))
    equivalent_metadata = []
    with zipfile.ZipFile(args.left) as a, zipfile.ZipFile(args.right) as b:
        for name in differences:
            if (name.endswith("/.megcfbt/package.json") and name in left and name in right
                    and left[name][1] == right[name][1]
                    and json.loads(a.read(name)) == json.loads(b.read(name))):
                equivalent_metadata.append(name)
    functional_differences = [name for name in differences if name not in equivalent_metadata]
    summary = {"file_count": len(left), "all_file_bytes_and_permissions_identical": not differences,
               "different_files": differences, "semantically_equivalent_package_metadata": equivalent_metadata,
               "gameplay_files_bytes_and_permissions_identical": not functional_differences,
               "functional_differences": functional_differences,
               "scope": "ZIP timestamps are excluded; package metadata JSON ordering is compared semantically; all other file bytes and permissions are compared exactly"}
    args.output.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    if functional_differences:
        raise SystemExit(1)
