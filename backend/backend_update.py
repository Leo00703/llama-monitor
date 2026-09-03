"""llama.cpp backend (llama-server build) updates: check / download / verify.

Unlike the app self-update (update.py — a git pull of the running panel),
swapping the backend is simple file work: the panel owns the llama-server
process, so the flow is stop → extract → verify `--version` → flip the
config → start. No running-exe lock dance is involved.

Release facts (ggml-org/llama.cpp, verified 2026-08-23):
- since v0.2.0 releases are two-track: `vX.Y.Z` stable tags ship NO
  binaries, only a `nightly-tag.txt` asset containing the pinned nightly
  tag; `b[NNNN]` nightly tags ship the prebuilt zips for every master
  commit. So the *stable channel* downloads the pinned nightly zip.
- Windows zips are flat (no wrapper folder): `llama-server.exe` sits at
  the zip root.
- `llama-server --version` prints to STDERR:
  `version: X.Y.Z-dev (build N, commit <sha>)` — official prebuilts report
  a real build number + commit; local/PR builds report `build 0, commit
  unknown`. That is the provenance signal (custom builds are never
  auto-updated).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from .config import DATA_DIR, no_window_kwargs, spawn_argv

log = logging.getLogger("llama-monitor.backend")

GITHUB_REPO = "ggml-org/llama.cpp"
API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"
USER_AGENT = "llama-monitor"
MANIFEST_NAME = "llama-monitor.json"
RELEASE_CACHE_TTL = 1800.0  # s — 2 checks/day + manual checks stay well within the API limit


class UpdateError(Exception):
    """Backend update failure with a user-facing message."""


@dataclass
class BuildInfo:
    version: str
    build: int
    commit: str

    @property
    def official(self) -> bool:
        # local/PR builds report "build 0, commit unknown"
        return self.build > 0 and self.commit not in ("", "unknown")

    @property
    def tag(self) -> Optional[str]:
        return f"b{self.build}" if self.official else None


_BTAG_RE = re.compile(r"^b(\d+)$")
_VERSION_RE = re.compile(
    r"version:\s*([0-9A-Za-z.+\-]+)\s*\(build\s*(\d+),\s*commit\s*([0-9a-fA-F]+|unknown)\)"
)

# Prebuilt asset name suffix per variant (deterministic, verified against
# the release pages). The cpu build is "win-cpu-x64" on Windows but plain
# "ubuntu-x64" on Linux; cuda prebuilts are Windows-only.
VARIANTS: dict[str, dict[str, str]] = {
    "cpu":       {"nt": "win-cpu-x64.zip",        "posix": "ubuntu-x64.tar.gz"},
    "vulkan":    {"nt": "win-vulkan-x64.zip",     "posix": "ubuntu-vulkan-x64.tar.gz"},
    "cuda-12.4": {"nt": "win-cuda-12.4-x64.zip"},
    "cuda-13.3": {"nt": "win-cuda-13.3-x64.zip"},
}


def server_exe_name() -> str:
    return "llama-server.exe" if os.name == "nt" else "llama-server"


def _platform_key() -> str:
    return "nt" if os.name == "nt" else "posix"


# run_version spawns a subprocess — noticeable on a saturated machine, and
# /api/backend/versions runs on EVERY page load. Cache the parsed result per
# (exe path, mtime) so a burst of page loads costs at most one spawn.
_PROV_TTL = 60.0
_prov_cache: dict[tuple[str, float], tuple[float, Optional["BuildInfo"]]] = {}


async def run_version(exe: str) -> Optional[BuildInfo]:
    """Run `<exe> --version` (printed to stderr) and parse the version line.

    Cached per (exe, mtime) for _PROV_TTL seconds (see _prov_cache)."""
    if not exe:
        return None
    try:
        key = (os.path.realpath(exe), os.path.getmtime(exe))
        hit = _prov_cache.get(key)
        if hit is not None and time.monotonic() - hit[0] < _PROV_TTL:
            return hit[1]
    except OSError:
        key = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *spawn_argv(exe, "--version"),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            # runs on EVERY page load (Backend.init → /api/backend/versions):
            # without CREATE_NO_WINDOW a windowless build flashes a console
            # window on each load (Windows) — same reason as nvidia-smi (#57)
            **no_window_kwargs(),
        )
    except (OSError, ValueError):
        return None
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=20)
    except (asyncio.TimeoutError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
        return None
    m = _VERSION_RE.search(err.decode("utf-8", "replace"))
    info = BuildInfo(m.group(1), int(m.group(2)), m.group(3)) if m else None
    if key is not None:
        if len(_prov_cache) >= 8:
            _prov_cache.clear()  # small TTL cache; bound it, never let it grow
        _prov_cache[key] = (time.monotonic(), info)
    return info


async def provenance(exe: str) -> dict[str, Any]:
    """Current build identity + provenance of the configured executable."""
    base: dict[str, Any] = {
        "exe": exe, "official": False, "known": False, "tag": None,
        "version": "", "build": 0, "commit": "", "folder": "", "error": None,
    }
    if not exe:
        base["error"] = "no llama-server executable configured"
        return base
    info = await run_version(exe)
    if info is None:
        base["error"] = "could not run 'llama-server --version'"
        return base
    base.update(
        version=info.version, build=info.build, commit=info.commit,
        official=info.official, tag=info.tag,
        folder=str(Path(exe).resolve().parent),
    )
    return base


# ----------------------------------------------------------------------
# release discovery (GitHub API)
# ----------------------------------------------------------------------

_rel_cache: dict[str, Any] = {"at": 0.0, "data": None}
_rel_lock = asyncio.Lock()
_rel_refreshing = False


async def fetch_releases(force: bool = False, stale_ok: bool = False) -> dict[str, Any]:
    """Latest stable tag + its pinned nightly + the latest nightly (b-tag).

    Cached for RELEASE_CACHE_TTL seconds; `force` bypasses the cache
    (manual "Check now"). Raises httpx errors to the caller.

    stale_ok (used by /api/backend/versions, which every page load calls):
    a stale-but-present cache is returned IMMEDIATELY and refreshed in the
    background — a cold GitHub call (30 s timeout) must never hold up a page
    load. Manual checks use stale_ok=False and always await fresh data.
    """
    if (not force and _rel_cache["data"]
            and time.time() - _rel_cache["at"] < RELEASE_CACHE_TTL):
        return _rel_cache["data"]
    if not force and stale_ok and _rel_cache["data"] is not None:
        await _kick_background_refresh()
        return _rel_cache["data"]
    async with _rel_lock:
        if (not force and _rel_cache["data"]
                and time.time() - _rel_cache["at"] < RELEASE_CACHE_TTL):
            return _rel_cache["data"]
        data = await _fetch_releases_network()
    _rel_cache["at"] = time.time()
    _rel_cache["data"] = data
    return data


async def _fetch_releases_network() -> dict[str, Any]:
    """The actual GitHub calls (releases/latest + releases list)."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=30, headers=headers,
                                 follow_redirects=True) as client:
        latest = (await client.get(f"{API_BASE}/releases/latest")).json()
        stable_tag = latest.get("tag_name") or ""
        pinned: Optional[str] = None
        for a in latest.get("assets", []):
            if a["name"] == "nightly-tag.txt":
                txt = (await client.get(a["browser_download_url"])).text.strip()
                if _BTAG_RE.match(txt):
                    pinned = txt
        rels = (await client.get(
            f"{API_BASE}/releases", params={"per_page": 15})).json()
        nightly: Optional[str] = None
        for r in rels:
            t = r.get("tag_name") or ""
            if _BTAG_RE.match(t):
                nightly = t
                break
    return {
        "stable_tag": stable_tag,
        "pinned_nightly": pinned,
        "latest_nightly": nightly,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


async def _kick_background_refresh() -> None:
    """Refresh the stale release cache in the background (one at a time).
    Failures keep the stale data; the next call retries."""
    global _rel_refreshing
    if _rel_refreshing:
        return
    _rel_refreshing = True

    async def _bg() -> None:
        global _rel_refreshing
        try:
            await fetch_releases(force=True)
        except Exception:
            pass
        finally:
            _rel_refreshing = False

    asyncio.create_task(_bg())


def asset_name_for(tag: str, variant: str) -> Optional[str]:
    """Exact release asset name for (tag, variant) on this platform."""
    suffix = VARIANTS.get(variant, {}).get(_platform_key())
    if not suffix:
        return None
    return f"llama-{tag}-bin-{suffix}"


async def find_asset(client: httpx.AsyncClient, tag: str, variant: str) -> Optional[dict]:
    """Asset dict (name/size/browser_download_url) for (tag, variant).

    Exact name first; then a prefix match as a safety net for variants
    whose suffix carries a version (e.g. rocm-7.14).
    """
    try:
        rel = (await client.get(f"{API_BASE}/releases/tags/{tag}")).json()
    except httpx.HTTPError as exc:
        log.warning("release lookup for %s failed: %s", tag, exc)
        return None
    if not isinstance(rel, dict) or rel.get("message"):
        return None
    want = asset_name_for(tag, variant)
    assets = rel.get("assets") or []
    if want:
        for a in assets:
            if a["name"] == want:
                return a
    prefix = f"llama-{tag}-bin-{variant}"
    for a in assets:
        n = a["name"]
        if n.startswith(prefix) and (n.endswith(".zip") or n.endswith(".tar.gz")):
            return a
    return None


# ----------------------------------------------------------------------
# download / extract / verify
# ----------------------------------------------------------------------

ProgressCb = Callable[[int, int], None]


async def download_file(asset: dict, dest: Path, progress: Optional[ProgressCb] = None) -> None:
    """Stream the release asset to dest (atomic replace; .part removed on failure)."""
    tmp = dest.parent / (dest.name + ".part")
    try:
        total = asset.get("size") or 0
        done = 0
        last_tick = 0.0
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=20),
                                     follow_redirects=True) as client:
            async with client.stream("GET", asset["browser_download_url"]) as resp:
                if resp.status_code != 200:
                    raise UpdateError(f"download failed (HTTP {resp.status_code})")
                with open(tmp, "wb") as f:
                    async for chunk in resp.aiter_bytes(256 * 1024):
                        f.write(chunk)
                        done += len(chunk)
                        now = time.time()
                        if progress and now - last_tick > 0.3:
                            last_tick = now
                            progress(done, total)
                if progress:  # fast (local) downloads may never hit the tick
                    progress(done, total)
        tmp.replace(dest)
    except BaseException:
        # never leave stale partials — retries used to re-download over them
        # and they accumulated as multi-GB orphans (#72)
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def extract_archive(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    elif archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as t:
            t.extractall(dest, filter="data")
    else:
        raise UpdateError(f"unsupported archive: {archive.name}")


async def verify_build(build_dir: Path, expected_tag: str) -> dict[str, Any]:
    """Run `--version` inside the extracted build; the flip needs a match."""
    exe = build_dir / server_exe_name()
    if not exe.exists():
        return {"ok": False, "error": f"{exe.name} not found in the extracted build"}
    info = await run_version(str(exe))
    if info is None:
        return {"ok": False, "error": "could not run --version on the new build"}
    if not info.official:
        return {"ok": False, "error": "extracted build reports no official build number"}
    if expected_tag and info.tag != expected_tag:
        return {"ok": False, "error": (
            f"version mismatch: expected {expected_tag}, "
            f"got {info.tag or info.version}")}
    return {"ok": True, "info": info}


def write_manifest(build_dir: Path, tag: str, variant: str,
                   url: str, size: int) -> None:
    manifest = {
        "tag": tag,
        "variant": variant,
        "source_url": url,
        "size_bytes": size,
        "installed_at": datetime.now().isoformat(timespec="seconds"),
    }
    (build_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def resolve_storage(config) -> Path:
    """Where downloaded builds live: the configured folder, else the
    sibling of the current build folder (its parent), else the data dir."""
    lb = getattr(config, "llama_backend", None)
    custom = (lb.storage_dir or "").strip() if lb else ""
    if custom:
        return Path(custom).expanduser()
    exe = config.resolved_exe()
    if exe:
        return Path(exe).resolve().parent.parent
    return DATA_DIR / "llama-builds"


def local_builds(storage: Path) -> list[dict[str, Any]]:
    """Panel-managed builds (dirs with a manifest), newest first."""
    out: list[dict[str, Any]] = []
    if not storage.is_dir():
        return out
    for d in sorted(storage.iterdir()):
        if not d.is_dir():
            continue
        manifest: dict = {}
        mp = d / MANIFEST_NAME
        if mp.exists():
            try:
                manifest = json.loads(mp.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                pass
        if not manifest:
            continue  # not a panel-managed build — leave it alone
        out.append({
            "dir": str(d),
            "name": d.name,
            "tag": manifest.get("tag") or "",
            "variant": manifest.get("variant") or "",
            "installed_at": manifest.get("installed_at") or "",
            "size_bytes": manifest.get("size_bytes") or 0,
            "has_server": (d / server_exe_name()).exists(),
        })
    # same-second installs tie on installed_at — the (zero-padded) tag is
    # then the newer-build discriminator
    out.sort(key=lambda b: (b["installed_at"] or "", b["tag"]), reverse=True)
    return out


def prune(storage: Path, keep: set[str]) -> list[str]:
    """Delete panel-managed build dirs whose name is not in `keep`."""
    deleted: list[str] = []
    if not storage.is_dir():
        return deleted
    for d in storage.iterdir():
        if not d.is_dir() or d.name in keep:
            continue
        if not (d / MANIFEST_NAME).exists():
            continue
        try:
            shutil.rmtree(d)
            deleted.append(d.name)
        except OSError:
            log.warning("could not prune build dir %s", d)
    return deleted


def free_bytes(path: Path) -> Optional[int]:
    try:
        return shutil.disk_usage(str(path)).free
    except OSError:
        return None


# Release asset names are deterministic (asset_name_for): llama-<tag>-bin-<...>
# where <tag> is a nightly b#### or a stable vX.Y(.Z). Match only that shape so
# user files that happen to be zips are never touched.
_ORPHAN_ARCHIVE_RE = re.compile(
    r"^llama-(?:b\d+|v[\d.]+(?:\.[A-Za-z0-9]+)*)-bin-.+\.(?:zip|tar\.gz)$")


def cleanup_partials(storage: Path) -> None:
    """Drop interrupted-download partials and orphan release archives
    (called at startup). Archives are only removed when they match the
    deterministic release-asset naming, so user files are never touched."""
    if not storage.is_dir():
        return
    for f in storage.iterdir():
        if not f.is_file():
            continue
        if f.name.endswith(".part") or _ORPHAN_ARCHIVE_RE.match(f.name):
            try:
                f.unlink()
            except OSError:
                pass


def suggest_variant() -> dict[str, str]:
    """Heuristic suggestion only — the user always makes the final call.

    nvidia-smi present → cuda (13.3 needs driver major >= 580, else
    12.4); no nvidia-smi → cpu.
    """
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5, check=False,
            **no_window_kwargs(),
        )
        if out.returncode == 0 and out.stdout.strip():
            driver = out.stdout.strip().splitlines()[0].strip()
            m = re.match(r"(\d+)\.", driver)
            major = int(m.group(1)) if m else 0
            variant = "cuda-13.3" if major >= 580 else "cuda-12.4"
            return {"variant": variant, "reason": f"NVIDIA driver {driver}"}
    except (OSError, subprocess.SubprocessError):
        pass
    return {"variant": "cpu", "reason": "no nvidia-smi (no NVIDIA GPU driver)"}


# ----------------------------------------------------------------------
# schedule
# ----------------------------------------------------------------------

def check_due(lb) -> bool:
    """True when a scheduled check is due: last check >12 h old, or a
    12 h slot boundary (00:00 / 12:00 local) was crossed since then."""
    last = (lb.last_check or "").strip()
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    now = datetime.now()
    if (now - last_dt).total_seconds() > 12 * 3600:
        return True
    return now.hour // 12 != last_dt.hour // 12
