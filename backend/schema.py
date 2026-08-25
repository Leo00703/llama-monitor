"""Semantic data models: presets, launch settings, speculative decoding.

Presets are stored as structured semantic settings, never as raw CLI
strings (plan 4.3). The translation to real flags lives in flags.py.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

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


class SpecSettings(BaseModel):
    spec_type: str = "none"
    draft_model: str = ""  # path relative to models_root
    draft_n_max: int = 3
    draft_n_min: int = 0
    # DSpark only: min acceptance confidence for block truncation
    # (--spec-draft-p-min); 0 = off. Emitted only when spec_type == draft-dspark.
    draft_conf_min: float = 0.0


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
    slots: int = -1  # -1 = auto; forced to 1 when spec_type != none
    cont_batching: str = "auto"  # auto | on | off
    kv_unified: str = "auto"  # auto | on | off

    # network & observability
    host: str = "0.0.0.0"
    port: int = 8080
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
