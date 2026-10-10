"""Validate links before materializing an independent source/runtime copy."""
from pathlib import Path


def validate_copy_tree(root: Path) -> None:
    resolved = root.resolve()
    def visit(folder, active):
        real = folder.resolve(strict=True)
        if real in active or len(active) > 256:
            raise ValueError(f"Source link creates a recursive directory copy: {folder}")
        for path in folder.iterdir():
            if path.name in {".git", ".hg", ".svn", ".DS_Store"}:
                continue
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                try:
                    target = path.resolve(strict=True)
                except (OSError, RuntimeError) as exc:
                    raise ValueError(f"Unusable source link: {path}") from exc
                if target != resolved and resolved not in target.parents:
                    raise ValueError(f"Source link escapes the selected directory: {path}")
            if path.is_dir():
                visit(path, active | {real})
    visit(root, set())
