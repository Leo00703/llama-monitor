"""Semantic data models: presets, launch settings, speculative decoding.

Presets are stored as structured semantic settings, never as raw CLI
strings (plan 4.3). The translation to real flags lives in flags.py.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

# --spec-type values (from llama-server --help, kept in sync manually)
SPEC_TYPES = [
    "none",
    "draft-simple",
    "draft-eagle3",
    "draft-mtp",
    "draft-dflash",
    "draft-dspark",
    "ngram-simple",
    "ngram-map-k",
    "ngram-map-k4v",
    "ngram-mod",
    "ngram-cache",
]

# draft-model types: all share ONE draft context, so at most one per launch
DRAFT_TYPES = (
    "draft-simple",
    "draft-eagle3",
    "draft-mtp",
    "draft-dflash",
    "draft-dspark",
)
# ngram types (stateless lookup tables; no drafter needed). Order = the
# server's fixed speculator priority (ngram-simple is tried first, ...).
NGRAM_TYPES = (
    "ngram-simple",
    "ngram-map-k",
    "ngram-map-k4v",
    "ngram-mod",
    "ngram-cache",
)


class NgramLookupSettings(BaseModel):
    """ngram-simple / ngram-map-k / ngram-map-k4v params
    (--spec-ngram-*-size-n, -size-m, -min-hits). Defaults = server defaults."""

    size_n: int = 12
    size_m: int = 48
    min_hits: int = 1


class NgramModSettings(BaseModel):
    """ngram-mod params (--spec-ngram-mod-n-match, -n-min, -n-max).
    Defaults = server defaults."""

    n_match: int = 24
    n_min: int = 48
    n_max: int = 64


class SpecSettings(BaseModel):
    # --spec-type: comma-separated list (issue #55). At most one draft-model
    # type (draft-*) plus any number of ngram types. The server tries the
    # impls in fixed priority order (all ngram types first, then the draft
    # type) — the first to produce a draft wins that step, so ngram acts as
    # the fast path and the draft model as fallback. Stored in canonical
    # order: draft type first, then ngram types in server priority order.
    spec_type: str = "none"
    draft_model: str = ""  # path relative to models_root
    draft_n_max: int = 3
    draft_n_min: int = 0
    # DSpark / DFlash: min acceptance confidence for block truncation
    # (--spec-draft-p-min); 0 = off. Emitted when spec_type is draft-dspark
    # or draft-dflash (DFlash2 honours the generic early-stop too).
    draft_conf_min: float = 0.0
    ngram_simple: NgramLookupSettings = Field(default_factory=NgramLookupSettings)
    ngram_map_k: NgramLookupSettings = Field(default_factory=NgramLookupSettings)
    ngram_map_k4v: NgramLookupSettings = Field(default_factory=NgramLookupSettings)
    ngram_mod: NgramModSettings = Field(default_factory=NgramModSettings)

    @field_validator("spec_type")
    @classmethod
    def _normalize_spec_type(cls, v: str) -> str:
        parts = [t.strip() for t in v.split(",") if t.strip()]
        if not parts:
            return "none"
        for t in parts:
            if t not in SPEC_TYPES:
                raise ValueError(
                    f"unknown --spec-type value '{t}' (valid: {', '.join(SPEC_TYPES)})"
                )
        if "none" in parts:
            return "none"
        seen: set[str] = set()
        uniq: list[str] = []
        for t in parts:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        drafts = [t for t in uniq if t in DRAFT_TYPES]
        if len(drafts) > 1:
            raise ValueError(
                "only one draft-model spec type is allowed per launch "
                f"(got: {', '.join(drafts)}) — pick one"
            )
        ngrams = [t for t in NGRAM_TYPES if t in uniq]
        return ",".join(drafts + ngrams) if (drafts or ngrams) else "none"

    @property
    def types(self) -> list[str]:
        """The enabled speculator types (empty for "none")."""
        return [] if self.spec_type == "none" else self.spec_type.split(",")

    @property
    def draft_type(self) -> str | None:
        """The enabled draft-model type, or None (ngram-only / off)."""
        for t in self.types:
            if t in DRAFT_TYPES:
                return t
        return None

    @property
    def ngram_types(self) -> list[str]:
        return [t for t in self.types if t in NGRAM_TYPES]

    @property
    def has_draft(self) -> bool:
        return self.draft_type is not None


class LaunchSettings(BaseModel):
    """Server launch parameters (plan 4.8). All model-related paths are
    relative to models_root (plan 4.5)."""

    # model & memory
    model: str = ""
    alias: str = ""
    mmproj: str = ""
    context_size: int = 4096
    n_gpu_layers: int = 99
    n_cpu_moe: int = 0
    override_tensors: list[str] = Field(default_factory=list)
    cache_type_k: str = "f16"
    cache_type_v: str = "f16"
    flash_attn: str = "auto"  # on | off | auto
    load_mode: str = "mmap"  # none | mmap | mlock | mmap+mlock | dio

    # multi-GPU
    tensor_split: list[int] = Field(default_factory=list)
    main_gpu: int = 0
    split_mode: str = "layer"  # none | layer | row

    # CPU & batching
    threads: int = 0  # 0 = auto
    threads_batch: int = 0  # 0 = same as threads
    batch_size: int = 2048
    micro_batch: int = 512
    cache_reuse: int = 0  # 0 = off

    # speculative decoding
    spec: SpecSettings = Field(default_factory=SpecSettings)

    # concurrency (parallel slots / continuous batching / unified KV).
    # "auto" = emit no flag, the server default applies (slots sized by
    # free memory, typically 2-4; unified KV enabled when slots is auto)
    slots: int = -1  # -1 = auto
    cont_batching: str = "auto"  # auto | on | off
    kv_unified: str = "auto"  # auto | on | off

    # network & observability
    host: str = "0.0.0.0"
    port: int = Field(8080, ge=1, le=65535)
    api_key: str = ""
    jinja: bool = True
    reasoning_preserve: bool = False
    merge_qkv: bool = False
    graph_reuse: int = 0
    fit: bool = False
    extra_flags: str = ""

    # generation defaults (plan 4.9) — injected per-request via the proxy,
    # saved here only for convenience as preset defaults
    generation: dict[str, Any] = Field(default_factory=dict)


class Preset(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = "New preset"
    launch: LaunchSettings = Field(default_factory=LaunchSettings)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "model": self.launch.model,
            "alias": self.launch.alias,
            "context_size": self.launch.context_size,
            "n_gpu_layers": self.launch.n_gpu_layers,
            "spec_type": self.launch.spec.spec_type,
            "port": self.launch.port,
            "updated_at": self.updated_at,
        }
