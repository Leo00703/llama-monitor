"""DSpark speculative decoding — `draft-dspark`.

DFlash plus a semi-autoregressive Markov head: each block position's
logits are biased by a low-rank term keyed on the previous token.
Currently only Qwen3-backbone drafts are supported.

The confidence threshold is --spec-draft-p-min: each drafted block is
truncated at the first position whose predicted acceptance falls below
it (default 0 = disabled). (The DSpark section of llama.cpp's
docs/speculative.md still shows the pre-rename name
--spec-draft-conf-min; the current flag list and source use p-min.)
"""

from __future__ import annotations

from ..schema import LaunchSettings, SpecSettings
from .base import Technique, Resolver


class _DSpark(Technique):
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


TECHNIQUE = _DSpark(
    spec_type="draft-dspark",
    label="draft-dspark",
    description="DFlash + Markov head (Qwen3-backbone drafts only); optional per-block confidence truncation.",
    needs_drafter=True,
    extra_fields=("draft_conf_min",),
)
