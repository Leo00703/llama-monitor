"""Application configuration (config.json), cross-platform via pathlib."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

APP_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_ROOT / "config.json"
EXAMPLE_PATH = APP_ROOT / "config.example.json"
DATA_DIR = APP_ROOT / "data"
PRESETS_DIR = DATA_DIR / "presets"


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
        path = Path(exe).expanduser()
        if path.exists():
            return str(path)
        if "/" not in exe and "\\" not in exe:
            found = shutil.which(exe)
            return found
        return None


def load_config() -> AppConfig:
    """Load config.json, seeding it from the example file on first run."""
    if not CONFIG_PATH.exists():
        if EXAMPLE_PATH.exists():
            shutil.copyfile(EXAMPLE_PATH, CONFIG_PATH)
        else:
            return AppConfig()
    try:
        return AppConfig.model_validate(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(f"config.json is invalid: {exc}") from exc


def save_config(cfg: AppConfig) -> None:
    """Atomically persist the configuration to config.json."""
    tmp = CONFIG_PATH.with_name("config.json.tmp")
    tmp.write_text(json.dumps(cfg.model_dump(), indent=2) + "\n", encoding="utf-8")
    tmp.replace(CONFIG_PATH)
