"""GGUF model browser: recursive scan of models_root, mmproj detection (plan 4.6)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

# The scan is O(files) stat syscalls — on Windows with Defender a folder of a
# few thousand files took ~16 s per request. Results are cached per root;
# new downloads appear after the TTL.
_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_lock = threading.Lock()


def list_models(root: Path) -> list[dict[str, Any]]:
    """List every .gguf file under `root` (mmproj files excluded from the list
    itself but attached to the model in their own directory)."""
    key = str(root)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit is not None and now - hit[0] < _CACHE_TTL:
            return hit[1]
    models = _scan(root)
    with _lock:
        _cache[key] = (now, models)
    return models


def _scan(root: Path) -> list[dict[str, Any]]:
    """Single pass over the tree: one walk, one stat per file, and mmproj
    files grouped by directory as they are found (the old implementation
    re-walked and re-statted each model's directory once per model)."""
    if not root.is_dir():
        return []
    models: list[dict[str, Any]] = []
    mmproj_by_parent: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*")):
        # fnmatch patterns are case-sensitive on Linux — match the .gguf
        # suffix in Python so MODEL.GGUF isn't missed there (#71)
        if not path.is_file() or path.suffix.lower() != ".gguf":
            continue
        rel = path.relative_to(root).as_posix()
        if path.name.lower().startswith("mmproj"):
            mmproj_by_parent.setdefault(str(path.parent), []).append(rel)
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        models.append({
            "path": rel,
            "name": path.name,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "mtime": stat.st_mtime,
            "mmproj": [],
        })
    # Attach mmproj siblings per directory (a single pass can't do this in
    # order: a sibling mmproj may sort before or after the model).
    for model in models:
        model["mmproj"] = sorted(
            mmproj_by_parent.get(str((root / model["path"]).parent), []))
    return models
