"""Application configuration, cross-platform via pathlib.

config.json and all persistent data (presets, analytics DB) live in a stable
per-user directory OUTSIDE the repository, so git operations (clone,
`git clean -fdx`, sync) can never wipe user data:

  Windows:  %APPDATA%/llama-monitor
  other:    $XDG_CONFIG_HOME/llama-monitor (default ~/.config/llama-monitor)

Override the location with the LLAMA_MONITOR_DATA environment variable.
Legacy data left in the repo (config.json, data/) is migrated automatically
on startup (idempotent, merge-based, never deletes data it cannot verify).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger("llama-monitor.config")

# Bundle root: the repo in a source run, the PyInstaller extraction dir
# (_MEIPASS) in a frozen one — bundled resources (config.example.json,
# frontend/, assets/) live here in both cases.
_BUNDLE_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_PATH = _BUNDLE_ROOT / "config.example.json"


def _legacy_root() -> Path:
    """Where in-repo legacy data (config.json, data/) lives.

    A frozen single-file build executes from a temp extraction dir, so
    __file__ is useless for legacy lookup — the legacy files sit next to
    the exe (the repo root in the standard workflow), hence the exe folder.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _BUNDLE_ROOT


LEGACY_CONFIG = _legacy_root() / "config.json"
LEGACY_DATA_DIR = _legacy_root() / "data"


def default_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "llama-monitor"


_override = os.environ.get("LLAMA_MONITOR_DATA", "").strip()
DATA_DIR = Path(_override).expanduser() if _override else default_data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
PRESETS_DIR = DATA_DIR / "presets"


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def migrate_legacy_data() -> None:
    """Merge old in-repo config/data into DATA_DIR (the single source of truth).

    Idempotent and merge-based: every legacy file is handled on its own, so a
    pre-existing destination never blocks the rest of the migration. The
    destination always wins a name collision (the live data dir stays
    authoritative); a legacy file whose content is already present in the
    destination is dropped, and anything that cannot be merged automatically
    (config.json, analytics.db, conflicting presets) is left in place with a
    warning — this function never deletes data it cannot verify.
    """
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"cannot create data directory {DATA_DIR}: {exc}") from exc

    if LEGACY_CONFIG.is_file():
        if CONFIG_PATH.exists():
            log.warning(
                "legacy config %s and live config %s both exist; both kept — "
                "merge manually if the legacy one holds values you need",
                LEGACY_CONFIG,
                CONFIG_PATH,
            )
        else:
            try:
                shutil.move(str(LEGACY_CONFIG), str(CONFIG_PATH))
                log.warning("migrated legacy config %s -> %s", LEGACY_CONFIG, CONFIG_PATH)
            except OSError as exc:
                log.error("could not migrate legacy config %s: %s", LEGACY_CONFIG, exc)

    if LEGACY_DATA_DIR.is_dir():
        presets_src = LEGACY_DATA_DIR / "presets"
        if presets_src.is_dir():
            PRESETS_DIR.mkdir(parents=True, exist_ok=True)
            moved = dropped = kept = 0
            for f in sorted(presets_src.iterdir()):
                if not f.is_file():
                    continue
                target = PRESETS_DIR / f.name
                if target.exists():
                    if _same_file(f, target):
                        try:
                            f.unlink()  # exact duplicate of the live preset
                            dropped += 1
                        except OSError as exc:
                            log.error("could not drop duplicate legacy preset %s: %s", f, exc)
                    else:
                        kept += 1  # conflict: live preset wins, legacy kept
                    continue
                try:
                    shutil.move(str(f), str(target))
                    moved += 1
                except OSError as exc:
                    log.error("could not migrate legacy preset %s: %s", f, exc)
            if moved:
                log.warning("migrated %d legacy preset(s) -> %s", moved, PRESETS_DIR)
            if dropped:
                log.warning(
                    "dropped %d legacy preset(s) already present in %s", dropped, PRESETS_DIR
                )
            if kept:
                log.warning(
                    "%d legacy preset(s) in %s conflict with the live %s — live kept, "
                    "legacy copy left in place",
                    kept,
                    presets_src,
                    PRESETS_DIR,
                )
            try:
                presets_src.rmdir()  # only succeeds once empty
            except OSError:
                pass

        db_src = LEGACY_DATA_DIR / "analytics.db"
        db_dst = DATA_DIR / "analytics.db"
        if db_src.is_file():
            if db_dst.exists():
                log.warning(
                    "legacy %s and live %s both exist; both kept "
                    "(SQLite files are not merged automatically)",
                    db_src,
                    db_dst,
                )
            else:
                try:
                    shutil.move(str(db_src), str(db_dst))
                    log.warning("migrated legacy %s -> %s", db_src, db_dst)
                except OSError as exc:
                    log.error("could not migrate legacy %s: %s", db_src, exc)

        try:
            if LEGACY_DATA_DIR.is_dir() and not any(LEGACY_DATA_DIR.iterdir()):
                LEGACY_DATA_DIR.rmdir()
        except OSError:
            pass


migrate_legacy_data()


class PanelSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class LlamaBackendPending(BaseModel):
    """A build that is available/downloaded but not yet applied."""

    tag: str = ""            # e.g. "b10588"
    variant: str = ""
    state: str = "available"  # available | downloaded


class LlamaBackendSettings(BaseModel):
    """llama.cpp backend (build) update settings — see backend_update.py."""

    channel: str = "stable"     # stable (pinned nightly) | nightly
    auto_download: bool = False
    variant: str = "cpu"        # cpu | vulkan | cuda-12.4 | cuda-13.3
    storage_dir: str = ""       # "" = sibling of the current build folder
    last_check: str = ""        # local ISO timestamp of the last check
    pending: Optional[LlamaBackendPending] = None


class AppConfig(BaseModel):
    """Live configuration, persisted to config.json (machine specific)."""

    llama_server_exe: str = ""
    models_root: str = ""
    default_server_port: int = 8080
    panel: PanelSettings = Field(default_factory=PanelSettings)
    active_preset_id: str = ""
    energy_price_eur_kwh: float = 0.20
    energy_overhead_w: float = 0.0
    update_check_minutes: int = Field(default=5, ge=0, le=1440)  # 0 = off
    llama_backend: LlamaBackendSettings = Field(default_factory=LlamaBackendSettings)

    def model_root(self) -> Optional[Path]:
        """Resolved models root directory, or None if unset."""
        if not self.models_root.strip():
            return None
        return Path(self.models_root).expanduser()

    def resolved_exe(self) -> Optional[str]:
        """Resolve the llama-server executable path (PATH lookup supported)."""
        exe = self.llama_server_exe.strip()
        if not exe:
            return None
        return resolve_exe_path(exe)


def resolve_exe_path(exe: str) -> Optional[str]:
    """Resolve an executable path, tolerating a directory that *contains* it.

    Users often paste the folder an extracted llama.cpp build lives in
    (e.g. ``C:\\llama-b10448-...\\``) instead of the server exe inside it.
    Windows' CreateProcess cannot launch a directory (it fails with WinError
    5, "access denied"), so we resolve to the exe within it — both the
    Windows (``llama-server.exe``) and the Linux/macOS (``llama-server``)
    names.
    """
    path = Path(exe).expanduser()
    if path.is_dir():
        for name in ("llama-server.exe", "llama-server"):
            candidate = path / name
            if candidate.exists():
                log.warning(
                    "llama_server_exe points at a directory; using %s", candidate
                )
                return str(candidate)
        log.error(
            "llama_server_exe points at a directory without llama-server: %s",
            path,
        )
        return None
    if path.exists():
        return str(path)
    if "/" not in exe and "\\" not in exe:
        return shutil.which(exe)
    return None


def spawn_argv(exe: str, *args: str) -> list[str]:
    """Build the argv used to launch the server executable.

    Windows' CreateProcess cannot execute .bat/.cmd files directly
    (it fails with WinError 5, "access denied"), so batch wrappers are
    routed through cmd.exe. Plain executables are returned unchanged.
    """
    if exe.lower().endswith((".bat", ".cmd")):
        return ["cmd.exe", "/c", exe, *args]
    return [exe, *args]


def no_window_kwargs() -> dict:
    """Spawn kwargs that keep console-app children (llama-server, nvidia-smi,
    ...) from flashing a console window when the panel runs windowless
    (frozen --noconsole build) on Windows. Harmless empty dict elsewhere."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def onefile_relaunch_env() -> dict[str, str]:
    """Environment for (re)launching the frozen onefile exe.

    PyInstaller >= 6.22 infers the onefile role (launcher vs application
    child) purely from the inherited ``_PYI_*`` variables and validates
    that a child's parent process is the same executable — so a running
    frozen app must never pass its own environment to a fresh copy of
    itself, or the new instance dies with "Security validation failure:
    parent process has different executable!". Strip the ``_PYI_*``
    variables and set the documented PYINSTALLER_RESET_ENVIRONMENT escape
    hatch (unconditional environment reset in the bootloader).
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI_")}
    if getattr(sys, "frozen", False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def load_config() -> AppConfig:
    """Load config.json, seeding it from the example file on first run."""
    if not CONFIG_PATH.exists():
        if EXAMPLE_PATH.exists():
            shutil.copyfile(EXAMPLE_PATH, CONFIG_PATH)
        else:
            return AppConfig()
    try:
        return AppConfig.model_validate(json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(f"config.json is invalid: {exc}") from exc


def save_config(cfg: AppConfig) -> None:
    """Atomically persist the configuration to config.json."""
    tmp = CONFIG_PATH.with_name("config.json.tmp")
    tmp.write_text(json.dumps(cfg.model_dump(), indent=2) + "\n", encoding="utf-8")
    tmp.replace(CONFIG_PATH)
