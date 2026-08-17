"""Semantic settings -> llama-server CLI flags translation (plan 4.4).

The FLAG_RULES list below is the single source of truth mapping semantic
settings to real CLI flags. If llama.cpp ever renames a flag (as happened
with --no-mmap/--mlock becoming --load-mode), only the affected rule needs
to change — presets are untouched.

build_args() also cross-checks the produced flags against the actually
installed binary (via `llama-server --help`): flags the binary doesn't
know are dropped with a warning instead of blocking the launch.
"""

from __future__ import annotations

import asyncio
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import spawn_argv
from .schema import DRAFT_MODEL_REQUIRED_TYPES, LaunchSettings

# ---------------------------------------------------------------------------
# cross-field validation
# ---------------------------------------------------------------------------


def validate_settings(
    s: LaunchSettings,
    gpu_count: int = 0,
    models_root: Optional[Path] = None,
) -> tuple[list[str], list[str]]:
    """Return (warnings, errors). Errors block the launch, warnings don't."""
    warnings: list[str] = []
    errors: list[str] = []

    if not s.model.strip():
        errors.append("model path is empty")

    if models_root is not None and not models_root.is_dir():
        warnings.append(f"models_root does not exist: {models_root}")

    if s.spec.spec_type == "draft-mtp" and s.mmproj.strip():
        errors.append(
            "mmproj (vision) and draft-mtp speculative decoding are incompatible — "
            "disable one of them"
        )

    if s.spec.spec_type in DRAFT_MODEL_REQUIRED_TYPES and not s.spec.draft_model.strip():
        errors.append(
            f"speculative decoding type '{s.spec.spec_type}' requires a drafter model "
            "(spec.draft_model)"
        )

    if gpu_count > 0 and s.tensor_split and len(s.tensor_split) != gpu_count:
        warnings.append(
            f"tensor-split has {len(s.tensor_split)} values but {gpu_count} GPUs were detected"
        )

    if s.split_mode == "tensor":
        warnings.append(
            "split-mode 'tensor' is incompatible with quantized KV cache"
        )

    return warnings, errors


# ---------------------------------------------------------------------------
# flag translation rules
# ---------------------------------------------------------------------------
# each builder returns the full argument tokens (flag + values) or None to skip.
# keep this list in sync with schema.LaunchSettings.


@dataclass
class FlagContext:
    models_root: Optional[Path] = None
    warnings: Optional[list[str]] = None  # filled during build

    def resolve(self, rel: str) -> str:
        """Resolve a model-relative path against models_root."""
        rel = rel.strip()
        p = Path(rel).expanduser()
        if p.is_absolute():
            return str(p)
        if self.models_root is not None:
            return str(self.models_root / p)
        if self.warnings is not None:
            self.warnings.append(f"models_root not configured, using path as-is: {rel}")
        return rel


def _r_model(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    if not s.model.strip():
        return None
    return ["-m", c.resolve(s.model)]


def _r_alias(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["-a", s.alias] if s.alias.strip() else None


def _r_mmproj(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    if not s.mmproj.strip():
        return None
    return ["-mm", c.resolve(s.mmproj)]


def _r_ctx(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["-c", str(s.context_size)] if s.context_size > 0 else None


def _r_ngl(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["-ngl", str(s.n_gpu_layers)] if s.n_gpu_layers > 0 else None


def _r_ncmoe(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--n-cpu-moe", str(s.n_cpu_moe)] if s.n_cpu_moe > 0 else None


def _r_override(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    if not s.override_tensors:
        return None
    return ["--override-tensor", ",".join(s.override_tensors)]


def _r_ctk(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--cache-type-k", s.cache_type_k] if s.cache_type_k else None


def _r_ctv(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--cache-type-v", s.cache_type_v] if s.cache_type_v else None


def _r_fa(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["-fa", s.flash_attn]


def _r_load(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--load-mode", s.load_mode]


def _r_split(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    if not s.tensor_split:
        return None
    return ["--tensor-split", ",".join(str(n) for n in s.tensor_split)]


def _r_main_gpu(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--main-gpu", str(s.main_gpu)] if s.main_gpu > 0 else None


def _r_split_mode(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--split-mode", s.split_mode]


def _r_threads(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["-t", str(s.threads)] if s.threads > 0 else None


def _r_threads_batch(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["-tb", str(s.threads_batch)] if s.threads_batch > 0 else None


def _r_batch(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["-b", str(s.batch_size)]


def _r_ubatch(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["-ub", str(s.micro_batch)]


def _r_cache_reuse(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--cache-reuse", str(s.cache_reuse)] if s.cache_reuse > 0 else None


def _r_spec_type(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--spec-type", s.spec.spec_type] if s.spec.spec_type != "none" else None


def _r_draft_model(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    if not s.spec.draft_model.strip():
        return None
    return ["--spec-draft-model", c.resolve(s.spec.draft_model)]


def _r_draft_n_max(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    if s.spec.spec_type == "none" or s.spec.draft_n_max <= 0:
        return None
    return ["--spec-draft-n-max", str(s.spec.draft_n_max)]


def _r_draft_n_min(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    if s.spec.spec_type == "none" or s.spec.draft_n_min <= 0:
        return None
    return ["--spec-draft-n-min", str(s.spec.draft_n_min)]


def _r_slots(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    slots = 1 if s.spec.spec_type != "none" else max(1, s.slots)
    return ["-np", str(slots)]


def _r_host(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--host", s.host]


def _r_port(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--port", str(s.port)]


def _r_api_key(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--api-key", s.api_key] if s.api_key.strip() else None


def _r_jinja(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--jinja"] if s.jinja else ["--no-jinja"]


def _r_reasoning(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--reasoning-preserve"] if s.reasoning_preserve else ["--no-reasoning-preserve"]


def _r_merge_qkv(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--merge-qkv"] if s.merge_qkv else None


def _r_graph_reuse(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["-gr", str(s.graph_reuse)] if s.graph_reuse > 0 else None


def _r_fit(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    return ["--fit", "on"] if s.fit else None


def _r_metrics(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    # always enabled: the dashboard depends on /metrics and /slots
    return ["--metrics", "--slots"]


def _r_extra(s: LaunchSettings, c: FlagContext) -> Optional[list[str]]:
    if not s.extra_flags.strip():
        return None
    try:
        return shlex.split(s.extra_flags)
    except ValueError:
        if c.warnings is not None:
            c.warnings.append(f"extra_flags could not be parsed: {s.extra_flags!r}")
        return None


FLAG_RULES: list[tuple[str, Callable[[LaunchSettings, FlagContext], Optional[list[str]]]]] = [
    ("model", _r_model),
    ("alias", _r_alias),
    ("mmproj", _r_mmproj),
    ("context_size", _r_ctx),
    ("n_gpu_layers", _r_ngl),
    ("n_cpu_moe", _r_ncmoe),
    ("override_tensors", _r_override),
    ("cache_type_k", _r_ctk),
    ("cache_type_v", _r_ctv),
    ("flash_attn", _r_fa),
    ("load_mode", _r_load),
    ("tensor_split", _r_split),
    ("main_gpu", _r_main_gpu),
    ("split_mode", _r_split_mode),
    ("threads", _r_threads),
    ("threads_batch", _r_threads_batch),
    ("batch_size", _r_batch),
    ("micro_batch", _r_ubatch),
    ("cache_reuse", _r_cache_reuse),
    ("spec_type", _r_spec_type),
    ("draft_model", _r_draft_model),
    ("draft_n_max", _r_draft_n_max),
    ("draft_n_min", _r_draft_n_min),
    ("slots", _r_slots),
    ("host", _r_host),
    ("port", _r_port),
    ("api_key", _r_api_key),
    ("jinja", _r_jinja),
    ("reasoning_preserve", _r_reasoning),
    ("merge_qkv", _r_merge_qkv),
    ("graph_reuse", _r_graph_reuse),
    ("fit", _r_fit),
    ("observability", _r_metrics),
    ("extra_flags", _r_extra),
]


def build_args(
    s: LaunchSettings,
    models_root: Optional[Path] = None,
    supported: Optional[set[str]] = None,
) -> tuple[list[str], list[str]]:
    """Translate semantic settings into CLI argument tokens.

    `supported` (from parse_supported_flags) enables the version check:
    unknown flags are dropped and reported as warnings (plan 4.4).
    Returns (args, warnings).
    """
    ctx = FlagContext(models_root=models_root, warnings=None)
    args: list[str] = []
    warnings: list[str] = []
    ctx.warnings = warnings

    for key, builder in FLAG_RULES:
        tokens = builder(s, ctx)
        if not tokens:
            continue
        if supported is not None:
            unknown = [t for t in tokens if t.startswith("-") and t not in supported]
            if unknown:
                warnings.append(
                    f"flag(s) {', '.join(unknown)} (setting: {key}) are not supported by "
                    f"this llama-server version — skipped"
                )
                continue
        args.extend(tokens)

    return args, warnings


# ---------------------------------------------------------------------------
# --help parsing (plan 4.4)
# ---------------------------------------------------------------------------

_HELP_FLAG_RE = re.compile(r"(?:^|\s)(--?[A-Za-z][A-Za-z0-9-]*)")

_help_cache: dict[tuple[str, float], set[str]] = {}


async def parse_supported_flags(exe: str) -> set[str]:
    """Run `llama-server --help` and collect every flag token it documents.

    Results are cached per (exe path, mtime). Returns an empty set on any
    failure (in which case no version check is performed).
    """
    try:
        path = Path(exe)
        key = (str(path), path.stat().st_mtime if path.exists() else 0.0)
        if key in _help_cache:
            return _help_cache[key]
        proc = await asyncio.create_subprocess_exec(
            *spawn_argv(exe, "--help"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        flags: set[str] = set()
        for line in out.decode(errors="replace").splitlines():
            for m in _HELP_FLAG_RE.finditer(line):
                flags.add(m.group(1))
        _help_cache[key] = flags
        return flags
    except (OSError, asyncio.TimeoutError):
        return set()
