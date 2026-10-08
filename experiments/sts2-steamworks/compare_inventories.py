"""Compare hash-only package observations; never authorize a conversion recipe."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


SOURCE_DATA = "data_sts2_windows_x86_64/"
TARGET_DATA = "data_sts2_linuxbsd_arm64/"


def canonical_hash(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verified_records(report):
    if (report.get("inventory_version") not in (1, 2)
            or report.get("inventory_complete") is not True or report.get("errors") != []):
        raise ValueError("expected a complete supported inventory without errors")
    files = report.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("expected nonempty file records")
    if canonical_hash(files) != report.get("tree_sha256"):
        raise ValueError("inventory checksum mismatch")
    records = {}
    for item in files:
        name = item.get("path")
        if (not isinstance(name, str) or not name or "\\" in name or ":" in name
                or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                or str(PurePosixPath(name)) != name):
            raise ValueError("expected a normalized relative file path")
        if name in records:
            raise ValueError("duplicate path")
        digest, size = item.get("sha256"), item.get("size_bytes")
        if (item.get("kind") != "file" or not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
                or type(size) is not int or size < 0):
            raise ValueError("expected regular-file records with SHA-256 and size")
        records[name] = item
    if report.get("files_hashed") != len(records):
        raise ValueError("file count mismatch")
    return records


def compare(source, prototype):
    left, right = verified_records(source), verified_records(prototype)
    result = {"comparison_version": 1, "source_tree_sha256": source["tree_sha256"],
              "prototype_tree_sha256": prototype["tree_sha256"],
              "scope": "Reported file hashes/sizes only. Exact data-directory rename for comparison, not a conversion, supported-build decision, or IL/asset validation.",
              "source_excluded": source.get("excluded", []),
              "prototype_excluded": prototype.get("excluded", []),
              "equal": [], "different": [], "source_only": [], "prototype_only": []}
    mapped = set()
    for name, item in sorted(left.items()):
        target = TARGET_DATA + name[len(SOURCE_DATA):] if name.startswith(SOURCE_DATA) else name
        if target in mapped:
            raise ValueError("data-directory mapping collision")
        mapped.add(target)
        other = right.get(target)
        record = {"source_path": name, "prototype_path": target,
                  "source_sha256": item["sha256"], "source_size_bytes": item["size_bytes"]}
        if other is None:
            result["source_only"].append(record)
            continue
        record.update(prototype_sha256=other["sha256"], prototype_size_bytes=other["size_bytes"])
        equal = (item["sha256"], item["size_bytes"]) == (other["sha256"], other["size_bytes"])
        result["equal" if equal else "different"].append(record)
    result["prototype_only"] = [right[name] for name in sorted(set(right) - mapped)]
    result["counts"] = {key: len(result[key]) for key in ("equal", "different", "source_only", "prototype_only")}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("prototype", type=Path)
    args = parser.parse_args()
    try:
        result = compare(json.loads(args.source.read_bytes()), json.loads(args.prototype.read_bytes()))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        parser.exit(2, "Inventory comparison refused: " + str(error) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
