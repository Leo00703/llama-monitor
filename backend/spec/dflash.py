"""DFlash speculative decoding — `draft-dflash`.

Block-diffusion draft: the draft model emits a whole block of tokens in
a single forward pass, injecting the target's hidden states into its
attention. --spec-draft-n-max is clamped by llama.cpp to the draft
model's trained block size.

DFlash2 (llama.cpp #27342) extends this with grouped dynamic depthwise
convolution + a candidate selector. There is NO separate --spec-type:
llama.cpp auto-detects DFlash2 from the draft checkpoint itself, so the
same `draft-dflash` type + `--spec-draft-model` covers both DFlash1 and
DFlash2 drafts (on a build that includes #27342). DFlash2 also honours
the generic --spec-draft-p-min early-stop.
"""

from __future__ import annotations

from ..schema import LaunchSettings, SpecSettings
from .base import DRAFTER_REQUIRED, Technique, Resolver


class _DFlash(Technique):
    def flags(self, spec: SpecSettings, resolve: Resolver) -> list[str]:
        out = super().flags(spec, resolve)
        if spec.draft_conf_min > 0:
            out.extend(["--spec-draft-p-min", f"{spec.draft_conf_min:.4g}"])
        return out

    def validate(self, s: LaunchSettings) -> list[str]:
        errors = super().validate(s)
        if not 0.0 <= s.spec.draft_conf_min <= 1.0:
            errors.append("spec.draft_conf_min must be between 0 and 1")
        return errors


TECHNIQUE = _DFlash(
    spec_type="draft-dflash",
    label="draft-dflash",
    description=(
        "Block-diffusion draft; emits a whole token block per forward pass. "
        "DFlash2 is auto-detected from the checkpoint (no separate type). "
        "n-max is clamped to the draft's trained block size."
    ),
    drafter=DRAFTER_REQUIRED,
    extra_fields=("draft_conf_min",),
)
