"""Application configuration, cross-platform via pathlib.

config.json and all persistent data (presets, analytics DB) live in a stable
per-user directory OUTSIDE the repository, so git operations (clone,
`git clean -fdx`, sync) can never wipe user data:

  Windows:  %APPDATA%/llama-monitor
  other:    $XDG_CONFIG_HOME/llama-monitor (default ~/.config/llama-monitor)

Override the location with the LLAMA_MONITOR_DATA environment variable.
Legacy data left in the repo (config.json, data/) is migrated automatically
on startup (one-way, idempotent).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

APP_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_PATH = APP_ROOT / "config.example.json"
LEGACY_CONFIG = APP_ROOT / "config.json"
LEGACY_DATA_DIR = APP_ROOT / "data"

log = logging.getLogger("llama-monitor.config")


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


def migrate_legacy_data() -> None:
    """Move old in-repo config/data to DATA_DIR. Idempotent, best-effort."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"cannot create data directory {DATA_DIR}: {exc}") from exc

    if LEGACY_CONFIG.exists() and not CONFIG_PATH.exists():
        try:
            shutil.move(str(LEGACY_CONFIG), str(CONFIG_PATH))
            log.warning("migrated legacy config %s -> %s", LEGACY_CONFIG, CONFIG_PATH)
        except OSError as exc:
            log.error("could not migrate legacy config %s: %s", LEGACY_CONFIG, exc)

    if LEGACY_DATA_DIR.is_dir():
        for name in ("presets", "analytics.db"):
            src = LEGACY_DATA_DIR / name
            dst = DATA_DIR / name
            if not src.exists() or dst.exists():
                continue
            try:
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                    moved = 0
                    for f in src.iterdir():
                        target = dst / f.name
                        if not target.exists():
                            shutil.move(str(f), str(target))
                            moved += 1
                    if moved:
                        log.warning("migrated legacy %s -> %s", src, dst)
                    try:
                        src.rmdir()  # only succeeds if empty now
                    except OSError:
                        pass
                else:
                    shutil.move(str(src), str(dst))
                    log.warning("migrated legacy %s -> %s", src, dst)
            except OSError as exc:
                log.error("could not migrate legacy %s: %s", src, exc)
        try:
            if LEGACY_DATA_DIR.is_dir() and not any(LEGACY_DATA_DIR.iterdir()):
                LEGACY_DATA_DIR.rmdir()
        except OSError:
            pass


migrate_legacy_data()


class PanelSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class AppConfig(BaseModel):
    """Live configuration, persisted to config.json (machine specific)."""

    llama_server_exe: str = ""
    models_root: str = ""
    default_server_port: int = 8080
    panel: PanelSettings = Field(default_factory=PanelSettings)
    active_preset_id: str = ""
    energy_price_eur_kwh: float = 0.20
    energy_overhead_w: float = 0.0

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
    (e.g. ``C:\\llama-b10448-...\\``) instead of the ``llama-server.exe``
    inside it. Windows' CreateProcess cannot launch a directory (it fails
    with WinError 5, "access denied"), so we resolve to the exe within it.
    """
    path = Path(exe).expanduser()
    if path.is_dir():
        candidate = path / "llama-server.exe"
        if candidate.exists():
            log.warning(
                "llama_server_exe points at a directory; using %s", candidate
            )
            return str(candidate)
        log.error(
            "llama_server_exe points at a directory without llama-server.exe: %s",
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
