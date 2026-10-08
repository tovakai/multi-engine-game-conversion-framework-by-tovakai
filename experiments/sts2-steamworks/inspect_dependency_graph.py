"""Read-only hash-guarded .NET dependency metadata; no deployment adaptation."""

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_SHA256 = "0620976a2fde3e57ebd1f1621efcd2da4809572cd093a61bb76f0f8ba9338837"
MAX_BYTES = 1048576


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property")
        result[key] = value
    return result


def object_value(value):
    if not isinstance(value, dict):
        raise ValueError("Expected a dependency JSON object")
    return value


def inspect(raw, expected_sha256):
    if len(raw) > MAX_BYTES:
        raise ValueError("Dependency file exceeds inspection limit")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ValueError("Dependency hash differs from inventory; metadata withheld")
    def refuse_constant(value):
        raise ValueError("Nonstandard JSON constant")
    document = object_value(json.loads(raw, object_pairs_hook=unique_object, parse_constant=refuse_constant))
    runtime = object_value(document.get("runtimeTarget"))
    targets = object_value(document.get("targets"))
    libraries = object_value(document.get("libraries"))
    if not isinstance(runtime.get("name"), str) or runtime["name"] not in targets:
        raise ValueError("Active runtime target is absent")
    records = []
    for target_name, target in sorted(targets.items()):
        rows = []
        for name, data in sorted(object_value(target).items()):
            object_value(data)
            if name not in libraries:
                raise ValueError("Target library has no metadata record")
            rows.append({"name": name, "record_sha256": canonical_hash(data),
                         "dependency_names": sorted(object_value(data.get("dependencies", {}))),
                         "managed_asset_count": len(object_value(data.get("runtime", {}))),
                         "native_asset_names": sorted(object_value(data.get("native", {}))),
                         "runtime_target_asset_count": len(object_value(data.get("runtimeTargets", {})))})
        records.append({"name": target_name, "library_count": len(rows), "libraries": rows})
    metadata = [{"name": name, "record_sha256": canonical_hash(object_value(data))}
                for name, data in sorted(libraries.items())]
    return {"diagnostic_version": 1, "sha256": actual, "size_bytes": len(raw),
            "scope": "Structured dependency metadata and canonical record hashes only; no execution, library loading, Steam calls, writes or conversion claims.",
            "runtime_target_name": runtime["name"], "targets": records,
            "library_metadata": metadata,
            "root_record_hashes": {name: canonical_hash(value) for name, value in sorted(document.items())},
            "errors": []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.path.is_symlink():
            raise ValueError("Symbolic link refused")
        with args.path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        report = inspect(raw, args.expected_sha256)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, "Dependency inspection refused: " + str(error) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
