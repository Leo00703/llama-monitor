"""App self-update from the git repository.

The whole app (code + bundled tray exe) is distributed as the git repo, so an
update is a fast-forward pull of the remote default branch in the repo root,
followed by a tray relaunch. This module only talks to git; the restart
handoff lives in tray.py (registered via ``set_restart_hook`` in main.py).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .config import no_window_kwargs

log = logging.getLogger("llama-monitor")

CHECK_TTL = 60.0        # seconds; /api/update/check reuses results within this
FETCH_TIMEOUT = 300.0   # updates download the bundled exe (~25MB) on slow lines
MAX_COMMITS = 10        # commit subjects surfaced to the UI

_lock = threading.Lock()
_cache: dict[str, Any] = {"ts": 0.0, "data": None}


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def repo_root() -> Optional[Path]:
    """The git checkout the app runs from (exe folder / dev checkout)."""
    if _frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _git(root: Path, *args: str, timeout: float = 60.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            **no_window_kwargs(),
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 128, "", f"git {args[0] if args else ''} failed: {exc}"


def _is_worktree(root: Optional[Path]) -> bool:
    if root is None or not root.exists():
        return False
    rc, out, _ = _git(root, "rev-parse", "--is-inside-work-tree")
    return rc == 0 and out == "true"


def _remote_ref(root: Path) -> Optional[str]:
    """Remote-tracking ref of the remote default branch (origin/HEAD)."""
    rc, _, _ = _git(root, "rev-parse", "--verify", "refs/remotes/origin/HEAD")
    if rc == 0:
        return "origin/HEAD"
    rc, sym, _ = _git(root, "symbolic-ref", "refs/remotes/origin/HEAD")
    if rc == 0 and sym.startswith("refs/remotes/origin/"):
        return sym[len("refs/remotes/"):]
    return None


def _read_buildinfo() -> Optional[dict[str, Any]]:
    """Build info baked into the frozen exe by CI (GITHUB_SHA + date)."""
    if _frozen():
        base = getattr(sys, "_MEIPASS", None)
        path = Path(base) / "backend" / "_buildinfo.json" if base else None
    else:
        path = Path(__file__).resolve().parent / "_buildinfo.json"
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    sha = str(data.get("sha") or "").strip()
    if not sha:
        return None
    return {"sha": sha[:9], "date": str(data.get("date") or ""), "source": "build"}


def current_version() -> dict[str, Any]:
    """Version of the RUNNING app: the frozen exe reports the commit it was
    built from; a dev checkout reports its live git HEAD."""
    if _frozen():
        info = _read_buildinfo()
        if info:
            return info
    root = repo_root()
    if _is_worktree(root):
        assert root is not None
        rc, sha, _ = _git(root, "rev-parse", "--short=9", "HEAD")
        if rc == 0 and sha:
            rc, date, _ = _git(root, "log", "-1", "--format=%cI", "HEAD")
            return {"sha": sha, "date": date or "", "source": "git"}
    return _read_buildinfo() or {"sha": "unknown", "date": "", "source": "none"}


def _check_now() -> dict[str, Any]:
    root = repo_root()
    out: dict[str, Any] = {
        "ok": True,
        "git": True,
        "repo": False,
        "origin": "",
        "current": current_version(),
        "latest": None,
        "behind": 0,
        "ahead": 0,
        "dirty": False,
        "commits": [],
        "error": None,
        "checked_at": time.time(),
    }
    if root is None or not root.exists():
        out["error"] = f"no repo found at {root}"
        return out
    if not _is_worktree(root):
        out["error"] = f"not a git checkout: {root}"
        return out
    out["repo"] = True
    rc, origin, _ = _git(root, "config", "--get", "remote.origin.url")
    out["origin"] = origin if rc == 0 else ""
    if not out["origin"]:
        out["error"] = "no origin remote configured"
        return out
    rc, _, err = _git(root, "fetch", "origin", "--quiet", "--prune", timeout=FETCH_TIMEOUT)
    if rc != 0:
        out["error"] = f"git fetch failed: {err or 'network error?'}"
        return out
    ref = _remote_ref(root)
    if ref is None:
        out["error"] = "could not determine the remote default branch"
        return out
    rc, latest_sha, _ = _git(root, "rev-parse", "--short=9", ref)
    if rc != 0:
        out["error"] = f"fetch produced no {ref} ref"
        return out
    rc, latest_date, _ = _git(root, "log", "-1", "--format=%cI", ref)
    out["latest"] = {"sha": latest_sha, "date": latest_date or ""}
    rc, behind, _ = _git(root, "rev-list", "--count", f"HEAD..{ref}")
    out["behind"] = int(behind) if rc == 0 and behind.isdigit() else 0
    rc, ahead, _ = _git(root, "rev-list", "--count", f"{ref}..HEAD")
    out["ahead"] = int(ahead) if rc == 0 and ahead.isdigit() else 0
    if out["behind"] > 0:
        rc, log_out, _ = _git(root, "log", "--format=%h%x1f%s", f"HEAD..{ref}")
        if rc == 0:
            for line in log_out.splitlines()[:MAX_COMMITS]:
                sha, _, subject = line.partition("\x1f")
                if sha:
                    out["commits"].append({"sha": sha, "subject": subject})
    dirty_lines = _dirty_lines(root)
    out["dirty"] = bool(dirty_lines)
    out["dirty_paths"] = dirty_lines[:8]
    return out


def _dirty_lines(root: Path) -> list[str]:
    """Changed TRACKED files (untracked strays don't block a ff-only merge,
    so they are excluded here and in apply_update())."""
    rc, out, _ = _git(root, "status", "--porcelain", "--untracked-files=no")
    if rc != 0:
        return []
    paths = []
    for line in out.splitlines():
        if not line.strip() or line.startswith("??"):
            continue
        # "XY path" (XY = two status chars; the leading space of a
        # worktree-only change is stripped away by _git, so split rather
        # than slice by a fixed offset).
        parts = line.split(None, 2)
        paths.append(parts[-1] if len(parts) > 1 else line.strip())
    return paths


def check(force: bool = False) -> dict[str, Any]:
    """Compare HEAD with the remote; results cached for CHECK_TTL seconds."""
    with _lock:
        if (
            not force
            and _cache["data"] is not None
            and time.time() - _cache["ts"] < CHECK_TTL
        ):
            return _cache["data"]
        try:
            data = _check_now()
        except Exception as exc:  # a check must never take the panel down
            log.exception("update check failed")
            data = {
                "ok": False, "git": True, "repo": False, "origin": "",
                "current": current_version(), "latest": None, "behind": 0,
                "ahead": 0, "dirty": False, "dirty_paths": [], "commits": [],
                "error": str(exc), "checked_at": time.time(),
            }
        _cache["ts"] = time.time()
        _cache["data"] = data
        return data


def _invalidate() -> None:
    with _lock:
        _cache["ts"] = 0.0
        _cache["data"] = None


def apply_update() -> dict[str, Any]:
    """Fast-forward pull of the remote default branch.

    Refuses a dirty tree or local divergence — the update never rewrites or
    discards local work.
    """
    root = repo_root()
    if not _is_worktree(root):
        return {"ok": False, "error": "app is not running from a git checkout"}
    assert root is not None
    rc, _, err = _git(root, "fetch", "origin", "--quiet", "--prune", timeout=FETCH_TIMEOUT)
    if rc != 0:
        return {"ok": False, "error": f"git fetch failed: {err or 'network error?'}"}
    ref = _remote_ref(root)
    if ref is None:
        return {"ok": False, "error": "could not determine the remote default branch"}
    dirty = _dirty_lines(root)
    if dirty:
        return {"ok": False, "error": "the repo has local changes — "
                                      "commit or revert them first: "
                                      + ", ".join(dirty[:5])
                                      + "  (git status shows the details)"}
    rc, ahead, _ = _git(root, "rev-list", "--count", f"{ref}..HEAD")
    if rc == 0 and ahead.isdigit() and int(ahead) > 0:
        return {"ok": False, "error": "local commits are ahead of the remote — push them first"}
    rc, out, err = _git(root, "merge", "--ff-only", ref, "--quiet", timeout=180.0)
    if rc != 0:
        return {"ok": False, "error": f"git merge failed: {err or out or 'unknown error'}"}
    _invalidate()
    log.info("update applied: fast-forwarded to %s", ref)
    return {"ok": True, "ref": ref}
