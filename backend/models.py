"""GGUF model browser: recursive scan of models_root, mmproj detection (plan 4.6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def list_models(root: Path) -> list[dict[str, Any]]:
    """List every .gguf file under `root` (mmproj files excluded from the list
    itself but attached to the model in their own directory)."""
    models: list[dict[str, Any]] = []
    if not root.is_dir():
        return models
    for path in sorted(root.rglob("*.gguf")):
        if not path.is_file() or path.name.lower().startswith("mmproj"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        models.append({
            "path": rel,
            "name": path.name,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "mtime": stat.st_mtime,
            "mmproj": find_mmproj(root, rel),
        })
    return models


def find_mmproj(root: Path, model_rel: str) -> list[str]:
    """mmproj*.gguf files living in the same directory as the model
    (case-insensitive), as POSIX paths relative to `root`."""
    parent = (root / model_rel).parent
    if not parent.is_dir():
        return []
    out: list[str] = []
    try:
        for f in sorted(parent.iterdir()):
            if f.is_file() and f.suffix.lower() == ".gguf" and f.name.lower().startswith("mmproj"):
                out.append(f.relative_to(root).as_posix())
    except OSError:
        return []
    return out
