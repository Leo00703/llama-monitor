"""llama.cpp backend (llama-server build) updates: check / download / verify.

Unlike the app self-update (update.py — a git pull of the running panel),
swapping the backend is simple file work: the panel owns the llama-server
process, so the flow is stop → extract → verify `--version` → flip the
config → start. No running-exe lock dance is involved.

Release facts (ggml-org/llama.cpp, verified against b11304, 2026-10):
- since v0.2.0 releases are two-track: `vX.Y.Z` stable tags ship NO
  binaries, only a `nightly-tag.txt` asset containing the pinned nightly
  tag; `b[NNNN]` nightly tags ship the prebuilt archives for every master
  commit. So the *stable channel* downloads the pinned nightly zip.
- the asset lines are NOT stable: a release ships win/ubuntu/macos/android
  × x64/arm64/s390x × cpu/vulkan/cuda/rocm/openvino/sycl/opencl, and the
  toolkit versions inside the names move (win-cuda-13.3 → 13.4, ROCm,
  OpenVINO). Nothing here declares them — `parse_build_asset` reads them
  (#85). CUDA prebuilts exist for Windows AND Linux.
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
import fnmatch
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
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

# ----------------------------------------------------------------------
# release asset discovery (#85)
# ----------------------------------------------------------------------
# Variant names are PARSED from the release, never declared here: llama.cpp
# renames its prebuilts whenever a toolkit bumps (cuda-13.3 -> cuda-13.4 in
# 2026-09, ROCm/OpenVINO regularly) and adds whole new lines (macOS, arm64,
# Linux CUDA). The old static table broke the updater on someone else's
# release day. Grammar, verified against b11304 (35 assets):
#   llama-<tag>-bin-<platform>[-<backend>[-<version>]][-<arch>].<zip|tar.gz>
#   cudart-llama-[-<tag>-]bin-<platform>-cuda-<version>-<arch>.<...>
# The arch token position is NOT fixed — `win-cpu-x64` and
# `linux-arm64-snapdragon` both occur. Non-`-bin-` assets (llama-ui.tar.gz,
# llama-<tag>-xcframework.zip) never match.
_BUILD_ASSET_RE = re.compile(
    r"^llama-(?P<tag>b\d+|v[\d.]+(?:-[0-9A-Za-z.]+)?)-bin-(?P<rest>.+?)\.(?:zip|tar\.gz)$")
_CUDART_ASSET_RE = re.compile(
    r"^cudart-llama-(?:(?P<tag>b\d+|v[\d.]+)-)?bin-(?P<rest>.+?)\.(?:zip|tar\.gz)$")

_ARCH_TOKENS = {"x64", "arm64", "arm", "s390x", "ppc64", "ppc64le", "riscv64",
                "loongarch64", "wasm32"}
_PLATFORM_TOKENS = {"win": "win", "windows": "win", "ubuntu": "linux",
                    "linux": "linux", "macos": "macos", "android": "android"}
_BACKEND_LABELS = {"cpu": "CPU", "vulkan": "Vulkan", "cuda": "CUDA",
                   "rocm": "ROCm", "openvino": "OpenVINO", "sycl": "SYCL",
                   "opencl": "OpenCL", "snapdragon": "Snapdragon",
                   "metal": "Metal"}
# Picker order: the plain build first, then Vulkan, then CUDA, then the rest.
_BACKEND_RANK = {"cpu": 0, "vulkan": 1, "cuda": 2}


def local_platform() -> str:
    """Asset-name platform token for this machine: win | linux | macos."""
    if os.name == "nt":
        return "win"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def local_arch() -> str:
    """Asset-name arch token for this machine (x64 / arm64 / ...)."""
    m = (platform.machine() or "").lower()
    if m in ("amd64", "x86_64", "x64"):
        return "x64"
    if m in ("arm64", "aarch64", "arm"):
        return "arm64"
    return m or "x64"


def _variant_id(backend: str, version: str) -> str:
    return "cpu" if backend == "cpu" else (f"{backend}-{version}" if version else backend)


def _parse_rest(rest: str) -> Optional[dict[str, Any]]:
    """`<platform>[-<backend>[-<version>]][-<arch>]` -> the match parts.

    None when the name is not a server build for a known platform/arch."""
    toks = rest.split("-")
    plat = _PLATFORM_TOKENS.get(toks[0])
    if plat is None or len(toks) < 2:
        return None
    arch = next((t for t in toks[1:] if t in _ARCH_TOKENS), "")
    if not arch:
        return None
    middle = [t for t in toks[1:] if t != arch]
    backend = middle[0] if middle else "cpu"
    version = ".".join(middle[1:])
    major = int(version.split(".")[0]) if version[:1].isdigit() else 0
    return {
        "platform": plat, "arch": arch, "backend": backend,
        "version": version, "major": major,
        "variant": _variant_id(backend, version),
        "label": _backend_label(backend, version),
    }


def _backend_label(backend: str, version: str) -> str:
    base = _BACKEND_LABELS.get(backend, backend.capitalize())
    return f"{base} {version}" if version else base


def parse_build_asset(name: str) -> Optional[dict[str, Any]]:
    """Parsed `llama-<tag>-bin-...` asset, or None (not a server build)."""
    m = _BUILD_ASSET_RE.match(name)
    if not m:
        return None
    parts = _parse_rest(m.group("rest"))
    if parts is None:
        return None
    return {"name": name, "tag": m.group("tag"), "kind": "build", **parts}


def parse_cudart_asset(name: str) -> Optional[dict[str, Any]]:
    """Parsed CUDA-runtime companion asset. Its tag segment is optional: the
    Windows asset carries none (the DLLs depend only on the CUDA major), the
    Linux one always carries the build tag."""
    m = _CUDART_ASSET_RE.match(name)
    if not m:
        return None
    parts = _parse_rest(m.group("rest"))
    if parts is None:
        return None
    return {"name": name, "tag": m.group("tag") or "", "kind": "cudart", **parts}


def is_valid_variant(variant: str) -> bool:
    """Shape check for a stored variant id (cpu / vulkan / cuda-13.4 /
    openvino-2026.4 / sycl-fp16 / ...). The set is open on purpose — it is
    whatever the release ships (#85), so it must not be an enum."""
    return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9.]+){0,3}", variant or ""))


def variants_available(assets: list[dict], plat: Optional[str] = None,
                       arch: Optional[str] = None) -> list[dict[str, Any]]:
    """The variants a release asset list ships for one platform+arch."""
    plat = local_platform() if plat is None else plat
    arch = local_arch() if arch is None else arch
    out: dict[str, dict[str, Any]] = {}
    for a in assets:
        p = parse_build_asset(a.get("name") or "")
        if not p or p["platform"] != plat or p["arch"] != arch:
            continue
        out.setdefault(p["variant"], {
            "variant": p["variant"], "label": p["label"], "backend": p["backend"],
            "version": p["version"], "major": p["major"], "arch": p["arch"],
            "platform": p["platform"], "asset": p["name"],
            "size_bytes": a.get("size") or 0,
        })
    return sorted(out.values(),
                  key=lambda v: (_BACKEND_RANK.get(v["backend"], 3), -v["major"], v["variant"]))


def server_exe_name() -> str:
    return "llama-server.exe" if os.name == "nt" else "llama-server"


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


# --list-devices output (common/arg.cpp common_print_available_devices):
#   Available devices:
#     CUDA0: NVIDIA GeForce RTX 5070 (8150 MiB, 7000 MiB free)
# or, when no non-CPU backend loads:
#   Available devices:
#     (none)
# With the CUDA runtime DLLs missing, ggml-cuda.dll fails to load SILENTLY
# (release builds) and the list is empty — so this is the build-proof
# functional check for a usable GPU (#81).
_PROBE_TTL = 60.0
_probe_cache: dict[tuple[str, float], tuple[float, dict]] = {}


def parse_devices(text: str) -> list[str]:
    """Non-CPU device lines from `--list-devices` output (empty = none)."""
    devices: list[str] = []
    in_list = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Available devices"):
            in_list = True
            continue
        if not in_list:
            continue
        if not s or s == "(none)":
            continue
        devices.append(s)
    return devices


async def probe_gpu(exe: str, timeout: float = 25.0, force: bool = False) -> dict:
    """Run `<exe> --list-devices` and report whether the server sees any
    non-CPU device.

    Returns {ok, gpu, devices, error}. Cached per (exe, mtime) for
    _PROBE_TTL seconds (GPU state changes on driver installs, which the
    user can force-recheck from the UI)."""
    res: dict[str, Any] = {"ok": False, "gpu": False, "devices": [], "error": ""}
    if not exe or not Path(exe).exists():
        res["error"] = "executable not found" if exe else "no executable configured"
        return res
    key = None
    if not force:
        try:
            key = (os.path.realpath(exe), os.path.getmtime(exe))
            hit = _probe_cache.get(key)
            if hit is not None and time.monotonic() - hit[0] < _PROBE_TTL:
                return dict(hit[1])
        except OSError:
            pass
    try:
        proc = await asyncio.create_subprocess_exec(
            *spawn_argv(exe, "--list-devices"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **no_window_kwargs(),
        )
    except (OSError, ValueError):
        res["error"] = "could not launch llama-server --list-devices"
        return res
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, OSError):
        with contextlib.suppress(OSError):
            proc.kill()
        res["error"] = "llama-server --list-devices timed out"
        return res
    res["ok"] = True
    res["devices"] = parse_devices(out.decode("utf-8", "replace"))
    res["gpu"] = bool(res["devices"])
    if key is not None:
        if len(_probe_cache) >= 8:
            _probe_cache.clear()
        _probe_cache[key] = (time.monotonic(), res)
    return res


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

# Per-tag asset lists (the release endpoint returns them). Seeded for free by
# the releases LIST call below, so /api/backend/versions (every page load) can
# answer "what does this release ship for this machine?" with no extra request.
_ASSETS_TTL = 900.0
_assets_cache: dict[str, tuple[float, list[dict]]] = {}


async def release_assets(client: httpx.AsyncClient, tag: str) -> list[dict]:
    """Raw asset list of one release tag (cached, `_ASSETS_TTL`)."""
    hit = _assets_cache.get(tag)
    if hit is not None and time.monotonic() - hit[0] < _ASSETS_TTL:
        return hit[1]
    try:
        rel = (await client.get(f"{API_BASE}/releases/tags/{tag}")).json()
    except httpx.HTTPError as exc:
        log.warning("release lookup for %s failed: %s", tag, exc)
        return hit[1] if hit else []
    assets = rel.get("assets") or [] if isinstance(rel, dict) else []
    if not isinstance(assets, list):
        assets = []
    if len(_assets_cache) >= 8:
        _assets_cache.clear()
    _assets_cache[tag] = (time.monotonic(), assets)
    return assets


def cached_variants(tag: str) -> list[dict[str, Any]]:
    """Variants this machine can install from `tag`, from the cache only
    (never a network call — /api/backend/versions runs on every page load).
    Empty when that release's assets were never fetched."""
    hit = _assets_cache.get(tag)
    if hit is None:
        return []
    return variants_available(hit[1])


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
        if isinstance(rels, list):
            # seed the asset cache for every release we already have in hand
            if len(_assets_cache) >= 8:
                _assets_cache.clear()
            for r in rels:
                t = r.get("tag_name") or ""
                if _BTAG_RE.match(t):
                    _assets_cache[t] = (time.monotonic(), r.get("assets") or [])
                    if nightly is None:
                        nightly = t
        # The stable channel's pinned nightly is normally far older than the
        # releases list (v0.5.0 pins b11146 while the list holds b11280+), so
        # its asset list must be fetched too — otherwise the variant picker
        # would be empty for the DEFAULT channel (#85). One extra call per
        # release-cache refresh (30 min TTL), never per request.
        if pinned and pinned not in _assets_cache:
            try:
                rel_p = (await client.get(f"{API_BASE}/releases/tags/{pinned}")).json()
                if isinstance(rel_p, dict) and not rel_p.get("message"):
                    _assets_cache[pinned] = (time.monotonic(), rel_p.get("assets") or [])
            except httpx.HTTPError:
                pass
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


async def find_asset(client: httpx.AsyncClient, tag: str, variant: str) -> Optional[dict]:
    """Asset dict (name/size/browser_download_url) for (tag, variant) on THIS
    machine — matched by (platform, arch, variant) parsed from the asset name,
    so a toolkit rename (cuda-13.3 -> cuda-13.4) is a non-event (#85)."""
    assets = await release_assets(client, tag)
    plat, arch = local_platform(), local_arch()
    for a in assets:
        p = parse_build_asset(a.get("name") or "")
        if p and p["platform"] == plat and p["arch"] == arch and p["variant"] == variant:
            return a
    # safety net for a name shape the parser did not anticipate
    prefix = f"llama-{tag}-bin-{variant}"
    for a in assets:
        n = a.get("name") or ""
        if n.startswith(prefix) and (n.endswith(".zip") or n.endswith(".tar.gz")):
            return a
    return None


def companion_supported(variant: str) -> bool:
    """Does this variant have a separate CUDA-runtime asset on this platform?
    Windows and Linux both ship one (the build links the NVIDIA runtime
    dynamically); macOS has no CUDA line at all."""
    return variant.startswith("cuda") and local_platform() in ("win", "linux")


async def find_companion_asset(
    client: httpx.AsyncClient, tag: str, variant: str
) -> Optional[dict]:
    """Asset dict for the CUDA runtime libraries, or None.

    None is valid and NOT an error: a future release may merge the runtime
    into the main archive (the probe stays the gate, so the install flow just
    stops fetching the extra file).

    Matching is EXACT on the CUDA line (variant) and on platform+arch — a
    cublas64_12 runtime must never be paired with a cuda-13.x build. A tagged
    companion (Linux) must also belong to this exact build."""
    if not companion_supported(variant):
        return None
    assets = await release_assets(client, tag)
    plat, arch = local_platform(), local_arch()
    for a in assets:
        c = parse_cudart_asset(a.get("name") or "")
        if not c or c["platform"] != plat or c["arch"] != arch:
            continue
        if c["variant"] != variant:
            continue
        if c["tag"] and c["tag"] != tag:
            continue
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
            # `filter` exists only on 3.12+; on older interpreters fall back
            # to the plain extract (trusted GitHub-release archives only, #73)
            if sys.version_info >= (3, 12):
                t.extractall(dest, filter="data")
            else:
                t.extractall(dest)
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


def read_manifest(build_dir: Path) -> Optional[dict]:
    """The panel manifest in a build dir, or None (not panel-managed / bad)."""
    p = build_dir / MANIFEST_NAME
    if not p.exists():
        return None
    try:
        m = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return m if isinstance(m, dict) else None


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


# The CUDA prebuilt does NOT contain the NVIDIA runtime libraries (they are
# separately licensed): they ship in the companion asset above. Without them
# the CUDA backend cannot load and — silently, in release builds — the server
# runs CPU-only (#81). The globs tolerate the CUDA major suffix
# (cublas64_12.dll vs cublas64_13.dll, libcublas.so.12 vs .so.13).
_CUDA_LIB_PATTERNS: dict[str, tuple[str, ...]] = {
    "win": ("cublas64*.dll", "cublasLt64*.dll", "cudart64*.dll"),
    "linux": ("libcublas.so*", "libcublasLt.so*", "libcudart.so*"),
}


def cuda_lib_patterns() -> tuple[str, ...]:
    return _CUDA_LIB_PATTERNS.get(local_platform(), ())


def missing_cuda_dlls(build_dir: Path) -> list[str]:
    """The CUDA runtime library globs still absent from the build folder
    (empty when the folder is self-sufficient). macOS has no CUDA line."""
    patterns = cuda_lib_patterns()
    if not patterns:
        return []
    try:
        names = {p.name for p in build_dir.iterdir() if p.is_file()}
    except OSError:
        return list(patterns)
    missing = []
    for pat in patterns:
        if not any(fnmatch.fnmatch(name, pat) for name in names):
            missing.append(pat)
    return missing


def record_cuda_runtime(build_dir: Path, url: str, size_bytes: int) -> None:
    """Record the installed companion CUDA-runtime asset in the panel
    manifest (diagnostics + repair). No-op when the manifest does not
    exist yet (the install flow writes it right before calling this)."""
    p = build_dir / MANIFEST_NAME
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(m, dict):
        return
    m["cuda_runtime"] = {
        "url": url,
        "size_bytes": size_bytes,
        "installed_at": datetime.now().isoformat(timespec="seconds"),
    }
    with contextlib.suppress(OSError):
        p.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")


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


# Release asset names are parsed (parse_build_asset): llama-<tag>-bin-<...>
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


def _ver_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", version or "")) or (0,)


# Driver major -> highest CUDA major the installed driver can run. NVIDIA's
# minor-version compatibility means a driver built for CUDA 13.0 runs every
# 13.x build, so only the MAJOR is compared (verified mapping: 525 -> 12.0,
# 550 -> 12.4, 570 -> 12.8, 580 -> 13.0).
_DRIVER_CUDA_MAJOR = ((580, 13), (525, 12))


def nvidia_driver_version() -> Optional[str]:
    """Driver version from nvidia-smi, or None (no NVIDIA driver / no tool)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5, check=False,
            **no_window_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return out.stdout.strip().splitlines()[0].strip()


def cuda_major_for_driver(driver: str) -> int:
    m = re.match(r"(\d+)", driver or "")
    if not m:
        return 0
    major = int(m.group(1))
    for driver_min, cuda_major in _DRIVER_CUDA_MAJOR:
        if major >= driver_min:
            return cuda_major
    return 0


def pick_suggested_variant(available: list[dict], driver: Optional[str],
                          plat: str, arch: str) -> dict[str, str]:
    """The suggestion decision, pure so it can be tested against a synthetic
    asset list. Always a SUGGESTION — the user makes the final call.

    `available` is variants_available() output for the target release."""
    if plat == "macos":
        # llama.cpp ships no separate Metal prebuilt: the macos build IS the
        # Metal build.
        return {"variant": "cpu", "reason": f"macOS {arch} build (CPU + Metal)"}
    if not available:
        return {"variant": "", "reason": "could not list this release's builds"}
    cpu = next((v for v in available if v["variant"] == "cpu"), None)
    if driver is None:
        v = cpu or available[0]
        return {"variant": v["variant"],
                "reason": "no nvidia-smi (no NVIDIA GPU driver)"}
    ceiling = cuda_major_for_driver(driver)
    fits = [v for v in available
            if v["backend"] == "cuda" and v["major"] and v["major"] <= ceiling]
    if fits:
        best = max(fits, key=lambda v: (v["major"], _ver_tuple(v["version"])))
        return {"variant": best["variant"],
                "reason": f"NVIDIA driver {driver} (CUDA {best['version']})"}
    shipped = ", ".join(v["variant"] for v in available if v["backend"] == "cuda")
    v = cpu or available[0]
    return {"variant": v["variant"], "reason": (
        f"NVIDIA driver {driver} runs at most CUDA {ceiling or 'unknown'}; "
        f"this release ships {shipped or 'no CUDA build'}")}


async def suggest_variant(tag: Optional[str] = None) -> dict[str, str]:
    """Heuristic suggestion from THIS machine + what the target release
    actually ships (#85) — never a hard-coded variant name."""
    plat, arch = local_platform(), local_arch()
    available: list[dict] = cached_variants(tag) if tag else []
    if tag and not available:
        headers = {"User-Agent": USER_AGENT}
        try:
            async with httpx.AsyncClient(timeout=30, headers=headers,
                                         follow_redirects=True) as client:
                available = variants_available(
                    await release_assets(client, tag))
        except httpx.HTTPError as exc:
            log.warning("variant suggestion: asset list for %s failed: %s", tag, exc)
    driver = None if plat == "macos" else await asyncio.to_thread(nvidia_driver_version)
    return pick_suggested_variant(available, driver, plat, arch)


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
