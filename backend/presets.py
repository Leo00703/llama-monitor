"""Preset CRUD, persisted as JSON files under data/presets/<id>.json."""

from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from .schema import LaunchSettings, Preset


class PresetStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------

    def _path(self, preset_id: str) -> Path:
        # avoid path traversal via ids
        safe = "".join(ch for ch in preset_id if ch.isalnum() or ch in "-_")
        return self._root / f"{safe}.json"

    def list(self) -> list[dict[str, Any]]:
        presets = [self.get(p.stem) for p in self._root.glob("*.json")]
        presets = [p for p in presets if p is not None]
        presets.sort(key=lambda p: p.updated_at, reverse=True)
        return [p.summary() for p in presets]

    def get(self, preset_id: str) -> Optional[Preset]:
        path = self._path(preset_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return Preset.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            return None

    def create(self, name: str, launch: LaunchSettings) -> Preset:
        preset = Preset(name=name, launch=launch)
        self._write(preset)
        return preset

    def update(
        self,
        preset_id: str,
        name: Optional[str] = None,
        launch: Optional[LaunchSettings] = None,
        generation: Optional[dict[str, Any]] = None,
    ) -> Optional[Preset]:
        preset = self.get(preset_id)
        if preset is None:
            return None
        if name is not None:
            preset.name = name
        if launch is not None:
            preset.launch = launch
        if generation is not None:
            preset.launch.generation = generation
        preset.updated_at = _now()
        self._write(preset)
        return preset

    def duplicate(self, preset_id: str, name: Optional[str] = None) -> Optional[Preset]:
        preset = self.get(preset_id)
        if preset is None:
            return None
        clone = copy.deepcopy(preset)
        clone.id = uuid.uuid4().hex[:12]
        clone.name = name or f"{preset.name} (copy)"
        clone.created_at = _now()
        clone.updated_at = _now()
        self._write(clone)
        return clone

    def delete(self, preset_id: str) -> bool:
        path = self._path(preset_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # ------------------------------------------------------------------

    def _write(self, preset: Preset) -> None:
        path = self._path(preset.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(preset.model_dump(), indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)


def _now() -> float:
    return time.time()
