"""Filesystem browse + path validation for the settings path pickers (#84).

GET /api/browse lists exactly ONE directory level (names only — never file
contents). Navigation is deliberately free (explicit issue decision): the
panel is an unauthenticated LAN tool whose model browser already walks
arbitrary subtrees, so chrooting the picker would only hide from honest
users what the API already exposes.

On Windows the parent of a drive root is the pseudo-path DRIVES_SENTINEL,
which lists the existing drive roots ("This PC" view).
"""

from __future__ import annotations

import asyncio
import os
import ssl
import string
from pathlib import Path
from typing import Any, Optional

from .backend_update import run_version
from .config import normalize_path_str, resolve_exe_path

# kind=cert picker shows these; "Show all files" reveals the rest
CERT_EXTS = {".pem", ".crt", ".key", ".cer", ".der", ".pfx", ".p12"}
# cap on files per listing (directories are always listed, uncounted)
MAX_FILES = 800
DRIVES_SENTINEL = "#drives"

_KINDS = {"dir", "exe", "cert"}


def browse_directory(path_str: str, kind: str = "dir", show_all: bool = False) -> dict[str, Any]:
    """One directory level for the path picker: {ok, at, parent, entries}."""
    kind = kind if kind in _KINDS else "dir"
    raw = normalize_path_str(path_str)
    if os.name == "nt" and raw.lower() == DRIVES_SENTINEL:
        drives = [
            {"name": f"{c}:\\", "path": f"{c}:\\", "dir": True, "size": None}
            for c in string.ascii_uppercase
            if Path(f"{c}:\\").exists()
        ]
        # at=None: "This PC" view — nothing to "select as folder"
        return {"ok": True, "at": None, "parent": None, "kind": kind, "entries": drives}

    target = _start_dir(raw)
    if target is None:
        return {"ok": False, "error": f"folder not found: {raw}"}
    try:
        listing = sorted(target.iterdir(), key=lambda p: (not _is_dir(p), p.name.casefold()))
    except PermissionError:
        return {"ok": False, "error": f"permission denied: {target}"}
    except OSError as exc:
        return {"ok": False, "error": f"{target}: {exc.strerror or exc}"}

    entries: list[dict[str, Any]] = []
    files = 0
    truncated = False
    for p in listing:
        is_dir = _is_dir(p)
        if not is_dir:
            if kind == "dir":
                continue  # folder pickers list folders only
            hidden = p.name.startswith(".")
            if hidden and not show_all:
                continue
            if kind == "cert" and not show_all and p.suffix.lower() not in CERT_EXTS:
                continue
            if files >= MAX_FILES:
                truncated = True
                continue
            files += 1
        try:
            size: Optional[int] = None if is_dir else p.stat().st_size
        except OSError:
            size = None
        entries.append({"name": p.name, "path": str(p), "dir": is_dir, "size": size})
    return {
        "ok": True,
        "at": str(target),
        "parent": _parent_of(target),
        "kind": kind,
        "entries": entries,
        "truncated": truncated,
    }


def _is_dir(p: Path) -> bool:
    try:
        return p.is_dir()
    except OSError:  # e.g. a symlink pointing at a dead/forbidden target
        return False


def _start_dir(raw: str) -> Optional[Path]:
    """Directory to open for a possibly empty / file / nonexistent start value.

    Empty → home. A file or a (partially) typed path walks up to the first
    real ancestor folder, so the picker always opens where the value lives.
    """
    target = Path(raw).expanduser() if raw else Path.home()
    while not target.is_dir():
        parent = target.parent
        if parent == target:
            return None
        target = parent
    return target


def _parent_of(target: Path) -> Optional[str]:
    if os.name == "nt":
        if target.parent == target:  # drive root → the drive list
            return DRIVES_SENTINEL
        return str(target.parent)
    if str(target) == "/":
        return None
    return str(target.parent)


# ----------------------------------------------------------------------
# field validation (POST /api/validate-paths)
# ----------------------------------------------------------------------


def _res(level: str, message: str) -> dict[str, str]:
    return {"level": level, "message": message}


async def validate_paths(body: dict[str, Any]) -> dict[str, Any]:
    """Validate settings path fields without writing anything.

    Only keys present in the body are validated. Levels: ok | warn | err |
    muted (neutral info, e.g. defaults). Read-only: never creates folders,
    never starts the configured exe beyond the cached `--version` probe.
    """
    out: dict[str, dict[str, str]] = {}

    if "exe" in body:
        out["exe"] = await _validate_exe(str(body.get("exe") or ""))

    if "models_root" in body:
        out["models_root"] = await _validate_models_root(str(body.get("models_root") or ""))

    if "storage_dir" in body:
        out["storage_dir"] = _validate_storage_dir(str(body.get("storage_dir") or ""))

    if "tls_cert" in body or "tls_key" in body:
        out.update(_validate_tls(
            str(body.get("tls_cert") or ""), str(body.get("tls_key") or "")))

    return {"ok": True, "results": out}


async def _validate_exe(value: str) -> dict[str, str]:
    exe = normalize_path_str(value)
    if not exe:
        return _res("warn", "not set — the server cannot be started")
    resolved = resolve_exe_path(exe)
    if resolved is None:
        return _res("err", "not found — check the path (a folder works too: "
                           "the llama-server exe inside it is picked up)")
    info = await run_version(resolved)
    if info is not None and info.build > 0:
        tag = info.tag or info.version
        return _res("ok", f"works — llama.cpp {tag} ({info.commit[:7]})")
    if info is not None:
        return _res("warn", "found, but its --version line is not a llama.cpp build")
    return _res("warn", "found, but it did not answer --version (is it an exe that runs?)")


async def _validate_models_root(value: str) -> dict[str, str]:
    root = normalize_path_str(value)
    if not root:
        return _res("muted", "not set — the model browser stays empty")
    path = Path(root).expanduser()
    if not path.exists():
        return _res("err", "folder not found")
    if not path.is_dir():
        return _res("err", "this is a file, not a folder")
    try:
        next(path.iterdir())
        readable = True
    except StopIteration:
        readable = True  # empty but readable
    except OSError:
        readable = False
    if not readable:
        return _res("err", "folder is not readable")
    count = await asyncio.to_thread(_count_gguf, path)
    if count:
        return _res("ok", f"{count} .gguf file(s) under this root")
    return _res("muted", "readable — no .gguf found yet (subfolders are searched too)")


def _count_gguf(root: Path, cap: int = 20000) -> int:
    """Count .gguf files under root, bounded (validation must stay snappy)."""
    count = scanned = 0
    for _, _, files in os.walk(root):
        scanned += len(files)
        count += sum(1 for f in files if f.lower().endswith(".gguf"))
        if scanned > cap:
            break
    return count


def _validate_storage_dir(value: str) -> dict[str, str]:
    raw = normalize_path_str(value)
    if not raw:
        return _res("muted", "not set — builds land next to the current build folder")
    path = Path(raw).expanduser()
    if path.exists():
        if not path.is_dir():
            return _res("err", "a file with this name already exists")
        if os.access(path, os.W_OK):
            return _res("ok", "existing folder, writable")
        return _res("err", "folder is not writable")
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    if os.access(probe, os.W_OK):
        return _res("muted", "doesn't exist yet — created on first download")
    return _res("err", "the parent folder is not writable")


def _validate_tls(cert_value: str, key_value: str) -> dict[str, dict[str, str]]:
    cert = normalize_path_str(cert_value)
    key = normalize_path_str(key_value)
    if not cert and not key:
        return {"tls_cert": _res("muted", "plain http — no TLS"), "tls_key": _res("muted", "")}
    if not cert or not key:
        msg = ("only one of the pair is set — cert and key are both needed, "
               "the panel stays on plain http without the pair")
        return {"tls_cert": _res("warn", msg), "tls_key": _res("warn", msg)}
    for kind, value in (("tls_cert", cert), ("tls_key", key)):
        if not Path(value).expanduser().is_file():
            return {kind: _res("err", "file not found")}
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ctx.load_cert_chain(Path(cert).expanduser(), Path(key).expanduser())
    except (OSError, ssl.SSLError) as exc:
        reason = getattr(exc, "strerror", None) or str(exc)
        return {"tls_cert": _res("err", f"cert/key pair rejected: {reason}"),
                "tls_key": _res("muted", "")}
    return {"tls_cert": _res("ok", "cert + key load — the panel serves HTTPS after restart"),
            "tls_key": _res("muted", "")}
