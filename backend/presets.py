"""Preset CRUD, persisted as JSON files under data/presets/<id>.json."""

from __future__ import annotations

import contextlib
import copy
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from .schema import LaunchSettings, Preset

log = logging.getLogger("llama-monitor.presets")


class PresetStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        # (#124) file name -> mtime signature of the last load failure;
        # keeps the warning-once-per-file invariant across repeated
        # (per-metrics-tick) get() calls on a broken active preset
        self._warned: dict[str, str] = {}

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
        preset, err = self._load(path)
        if err is not None:
            self._warn_broken(path, err)
        return preset

    def broken(self) -> list[dict[str, Any]]:
        """(#124) JSON files that exist but cannot be loaded. A preset that
        fails validation (schema drift after a panel update) or is corrupt
        (half-written JSON) used to vanish with no trace; the Presets page
        shows these as red "unreadable" rows the user can inspect (error
        text) and delete — it is their data, hiding it silently is not
        acceptable."""
        out: list[dict[str, Any]] = []
        for p in sorted(self._root.glob("*.json")):
            _, err = self._load(p)
            if err is None:
                continue
            name = p.stem
            with contextlib.suppress(Exception):
                raw = json.loads(p.read_text(encoding="utf-8-sig"))
                if isinstance(raw, dict) and isinstance(raw.get("name"), str) and raw["name"]:
                    name = raw["name"]
            out.append({"id": p.stem, "name": name, "error": err})
        return out

    def _load(self, path: Path) -> tuple[Optional[Preset], Optional[str]]:
        """(preset, error): error is None on success, else a short
        human-readable reason. Deliberately distinguishes the failure
        classes — "corrupt JSON" vs "not a valid preset" points at a
        different cause (power loss/AV write vs panel/schema drift)."""
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return Preset.model_validate(data), None
        except OSError as exc:
            return None, f"could not read file: {type(exc).__name__}: {exc}"
        except json.JSONDecodeError as exc:
            return None, f"corrupt JSON: {exc}"
        except ValidationError as exc:
            errs = exc.errors()
            first = errs[0] if errs else {}
            loc = ".".join(str(x) for x in first.get("loc", ()))
            return None, f"not a valid preset: {loc}: {first.get('msg', 'validation error')}"

    def _warn_broken(self, path: Path, err: str) -> None:
        try:
            st = path.stat()
            sig = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            sig = "?"
        if self._warned.get(path.name) == sig:
            return  # already warned about this exact file state
        self._warned[path.name] = sig
        log.warning("preset %s failed to load: %s", path.name, err)

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
            old_generation = preset.launch.generation
            preset.launch = launch
            if not launch.generation and generation is None:
                # the presets editor replaces the whole launch object with an
                # empty generation block — carry the saved defaults over so a
                # launch save doesn't silently wipe them (#50); the dedicated
                # /generation endpoint is the only way to clear them
                preset.launch.generation = old_generation
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
