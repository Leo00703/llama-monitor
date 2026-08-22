"""App self-update from the git repository.

The whole app (code + bundled tray exe) is distributed as the git repo, so an
update is a fast-forward pull of the remote default branch in the repo root,
followed by a tray relaunch. This module only talks to git; the restart
handoff lives in tray.py (registered via ``set_restart_hook`` in main.py).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .config import DATA_DIR, no_window_kwargs, onefile_relaunch_env

log = logging.getLogger("llama-monitor")

CHECK_TTL = 60.0        # seconds; /api/update/check reuses results within this
FETCH_TIMEOUT = 300.0   # updates download the bundled exe (~25MB) on slow lines
MAX_COMMITS = 10        # commit subjects surfaced to the UI
BOOTSTRAP_WAIT_SECONDS = 90  # max wait for the old process to exit (helper)

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


# ---------------------------------------------------------------------------
# Deferred update (frozen Windows): the bootstrap helper
#
# Windows locks a running exe, so `git merge` cannot replace
# llama-monitor.exe while this process is alive — and every CI refresh
# commit ships a new exe. The merge therefore runs in a helper that is NOT
# the app: this process stages it (fetch + PowerShell script below), exits,
# and the helper waits for the PID to die, merges, and relaunches the app
# (success or failure, so the user always gets a running panel + a result
# toast). PowerShell (not .bat): `tasklist`/`timeout` silently die in a
# detached console-less process, while PowerShell and git work fine there.
# ---------------------------------------------------------------------------


def _result_path() -> Path:
    return DATA_DIR / "update-result.txt"


def _ps_str(value: str) -> str:
    """Quote a value for a double-quoted PowerShell string literal."""
    return value.replace('"', '`"').replace("$", "`$")


def _write_bootstrap_ps1(
    root: Path, app_path: Path, old_pid: int, result_path: Path, ref: str
) -> Path:
    """Write the update bootstrap script (run detached by _start_deferred)."""
    ps = (
        "$ErrorActionPreference = 'Continue'\r\n"
        f"$oldPid = {old_pid}\r\n"
        f"$repo = \"{_ps_str(str(root))}\"\r\n"
        f"$app = \"{_ps_str(str(app_path))}\"\r\n"
        f"$result = \"{_ps_str(str(result_path))}\"\r\n"
        f"$ref = \"{_ps_str(ref)}\"\r\n"
        f"$waitMax = {BOOTSTRAP_WAIT_SECONDS}\r\n"
        "while ($waitMax -gt 0) {\r\n"
        "  $p = Get-Process -Id $oldPid -ErrorAction SilentlyContinue\r\n"
        "  if (-not $p) { break }\r\n"
        "  $waitMax -= 1\r\n"
        "  Start-Sleep -Seconds 1\r\n"
        "}\r\n"
        # A onefile exe runs as TWO processes (parent bootstrap + app child,\r\n"
        # both with Path == $app); the parent keeps the exe image mapped\r\n"
        # until it exits, and git cannot replace a mapped exe. Wait until\r\n"
        # nothing runs from $app AND the file opens exclusively (the\r\n"
        # definitive test that git can replace it). Merging while it is\r\n"
        # locked leaves a PARTIAL merge (frontend/* written, exe not) and a\r\n"
        # dirty tree - so on timeout report the failure and skip the merge.\r\n"
        "$exeFree = $false\r\n"
        "function Test-ExeFree {\r\n"
        "  $live = $false\r\n"
        "  foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) {\r\n"
        "    try { if ($p.Path -eq $app) { $live = $true; break } } catch {}\r\n"
        "  }\r\n"
        "  if ($live) { return $false }\r\n"
        "  try {\r\n"
        "    $h = [System.IO.File]::Open($app, 'Open', 'ReadWrite', 'None')\r\n"
        "    $h.Close()\r\n"
        "    return $true\r\n"
        "  } catch { return $false }\r\n"
        "}\r\n"
        "$grace = 10\r\n"
        "while ($grace -gt 0) {\r\n"
        "  if (Test-ExeFree) { $exeFree = $true; break }\r\n"
        "  $grace -= 1\r\n"
        "  Start-Sleep -Seconds 1\r\n"
        "}\r\n"
        # The parent may be STUCK instead of gone: if Windows cannot delete\r\n"
        # its _MEI* temp dir (antivirus scan, locked file) the bootloader\r\n"
        # sits on a 'Failed to remove temporary directory' dialog and the\r\n"
        # exe stays mapped forever - unattended (remote) updates can never\r\n"
        # complete. The app child is already gone (loop 1); a HEALTHY running\r\n"
        # instance always has its app child alive, so an exe process WITHOUT\r\n"
        # a live child is the stuck bootloader parent - safe to force-kill\r\n"
        # (the dialog dies with it).\r\n"
        "$killedNote = ''\r\n"
        "if (-not $exeFree) {\r\n"
        "  $stuck = @()\r\n"
        "  foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) {\r\n"
        "    try {\r\n"
        "      if ($p.Path -eq $app) {\r\n"
        "        $kids = Get-CimInstance Win32_Process -Filter \"ParentProcessId = $($p.Id)\" -ErrorAction SilentlyContinue\r\n"
        "        if (-not $kids) { $stuck += $p }\r\n"
        "      }\r\n"
        "    } catch {}\r\n"
        "  }\r\n"
        "  if ($stuck.Count -gt 0) {\r\n"
        "    $killedNote = 'note: force-killed stuck launcher process(es) ' + (($stuck | ForEach-Object { $_.Id }) -join ', ') + ' that blocked the exe (e.g. temp-dir cleanup dialog)'\r\n"
        "    foreach ($p in $stuck) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }\r\n"
        "    $retry = 30\r\n"
        "    while ($retry -gt 0) {\r\n"
        "      if (Test-ExeFree) { $exeFree = $true; break }\r\n"
        "      $retry -= 1\r\n"
        "      Start-Sleep -Seconds 1\r\n"
        "    }\r\n"
        "  }\r\n"
        "}\r\n"
        "if (-not $exeFree) {\r\n"
        "  'RESULT:fail' | Out-File -LiteralPath $result -Append -Encoding utf8\r\n"
        "  if ($killedNote) { $killedNote | Out-File -LiteralPath $result -Append -Encoding utf8 }\r\n"
        "  'error: llama-monitor.exe is still locked (a previous instance is still running) - quit it and retry the update' | Out-File -LiteralPath $result -Append -Encoding utf8\r\n"
        "  Remove-Item -LiteralPath $PSCommandPath -ErrorAction SilentlyContinue\r\n"
        "  exit 0\r\n"
        "}\r\n"
        "'pending' | Set-Content -LiteralPath $result -Encoding utf8\r\n"
        "if ($killedNote) { $killedNote | Out-File -LiteralPath $result -Append -Encoding utf8 }\r\n"
        "$gitOut = & git -C $repo merge --ff-only $ref 2>&1\r\n"
        "$gitOut | Out-File -LiteralPath $result -Append -Encoding utf8\r\n"
        "if ($LASTEXITCODE -ne 0) {\r\n"
        "  'RESULT:fail' | Out-File -LiteralPath $result -Append -Encoding utf8\r\n"
        "} else {\r\n"
        "  $sha = & git -C $repo rev-parse --short HEAD 2>$null\r\n"
        "  'RESULT:ok' | Out-File -LiteralPath $result -Append -Encoding utf8\r\n"
        "  \"SHA:$sha\" | Out-File -LiteralPath $result -Append -Encoding utf8\r\n"
        "}\r\n"
        "# The old app's env carries PyInstaller onefile role vars (_PYI_*);\r\n"
        "# PyInstaller >= 6.22 would treat the relaunched exe as a spoofed\r\n"
        "# onefile child and refuse to start (security validation). Strip\r\n"
        "# them and force the documented environment reset.\r\n"
        "Remove-Item Env:_PYI_* -ErrorAction SilentlyContinue\r\n"
        "$env:PYINSTALLER_RESET_ENVIRONMENT = '1'\r\n"
        "try { Start-Process -FilePath $app } catch {}\r\n"
        "Remove-Item -LiteralPath $PSCommandPath -ErrorAction SilentlyContinue\r\n"
    )
    ps_path = DATA_DIR / "update-bootstrap.ps1"
    ps_path.write_text(ps, encoding="ascii")
    return ps_path


def _start_deferred(
    root: Path, ref: str, app_path: Path, old_pid: int
) -> dict[str, Any]:
    """Stage the bootstrap helper and launch it detached; caller must exit."""
    result_path = _result_path()
    ps_path = _write_bootstrap_ps1(root, app_path, old_pid, result_path, ref)
    kwargs = dict(no_window_kwargs())
    if os.name == "nt":
        # NO_WINDOW + NEW_PROCESS_GROUP, NOT DETACHED_PROCESS: empirically a
        # powershell launched DETACHED dies silently at startup on Windows
        # (verified: no script execution, rc 0, no output).
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP
    kwargs.update(close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Never hand the frozen app's environment (which carries the onefile
    # _PYI_* role vars) to the helper — see onefile_relaunch_env().
    kwargs["env"] = onefile_relaunch_env()
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(ps_path)],
            **kwargs,
        )
    except OSError as exc:
        return {"ok": False, "error": f"failed to start the update helper: {exc}"}
    log.info("update: deferred bootstrap started (%s, old pid %s)", ps_path, old_pid)
    return {"ok": True, "ref": ref, "deferred": True}


def consume_update_result() -> Optional[dict[str, Any]]:
    """One-shot outcome of a deferred bootstrap update, if pending.

    The helper writes ``<data-dir>/update-result.txt`` (``pending``, the git
    output, then ``RESULT:ok`` + ``SHA:`` or ``RESULT:fail``); this reads and
    deletes it. Returns ``None`` when there is nothing to report.
    """
    path = _result_path()
    try:
        if not path.exists():
            return None
        # utf-8-sig: PowerShell 5.1 writes a UTF-8 BOM with -Encoding utf8
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    try:
        path.unlink()
    except OSError:
        pass
    ok: Optional[bool] = None
    sha = ""
    git_lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("RESULT:ok"):
            ok = True
        elif s.startswith("RESULT:fail"):
            ok = False
        elif s.startswith("SHA:"):
            sha = s[4:].strip()
        elif s and s != "pending":
            git_lines.append(s)
    if ok is None:
        return {
            "ok": False,
            "error": "the update was interrupted before it finished — check "
                     "`git status` in the repo folder and run `git pull` manually",
        }
    if ok:
        return {"ok": True, "sha": sha}
    err = next(
        (
            l
            for l in git_lines
            if l.startswith("fatal") or "error" in l.lower()
        ),
        git_lines[-1] if git_lines else "git merge failed",
    )
    return {"ok": False, "error": err[:300]}


def apply_update() -> dict[str, Any]:
    """Fast-forward pull of the remote default branch.

    Refuses a dirty tree or local divergence — the update never rewrites or
    discards local work. Frozen on Windows the merge is deferred to the
    bootstrap helper (the running exe is locked by Windows until this
    process exits; the helper merges and relaunches the app).
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
        if not (_frozen() and os.name == "nt"):
            return {"ok": False, "error": "the repo has local changes — "
                                          "commit or revert them first: "
                                          + ", ".join(dirty[:5])
                                          + "  (git status shows the details)"}
        # Frozen deployment checkouts are never edited by hand, so a dirty
        # tree is a leftover from an interrupted update (the merge died
        # mid-checkout, e.g. the exe was still locked by the onefile parent
        # and the frontend files had already been written). Restore the tree
        # to HEAD and let the ff merge below re-apply the changes cleanly.
        rc, out, err = _git(root, "reset", "--hard", "HEAD")
        if rc != 0:
            return {"ok": False, "error": "the repo has local changes and the "
                                          "automatic recovery failed: "
                                          + (err or out or "git reset --hard HEAD")}
        log.warning("update: discarded leftover local change(s) before the "
                    "update: %s", ", ".join(dirty[:10]))
    rc, ahead, _ = _git(root, "rev-list", "--count", f"{ref}..HEAD")
    if rc == 0 and ahead.isdigit() and int(ahead) > 0:
        return {"ok": False, "error": "local commits are ahead of the remote — push them first"}
    # Frozen on Windows: the running exe is locked by Windows, so the merge
    # must run in the bootstrap helper AFTER this process exits (it
    # relaunches the app itself — the restart hook must not spawn anything).
    if _frozen() and os.name == "nt":
        return _start_deferred(root, ref, Path(sys.executable), os.getpid())
    rc, out, err = _git(root, "merge", "--ff-only", ref, "--quiet", timeout=180.0)
    if rc != 0:
        return {"ok": False, "error": f"git merge failed: {err or out or 'unknown error'}"}
    _invalidate()
    log.info("update applied: fast-forwarded to %s", ref)
    return {"ok": True, "ref": ref}
