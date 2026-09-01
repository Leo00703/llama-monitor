"""MTP (multi-token prediction) speculative decoding — `draft-mtp`.

The drafter is the target model's own built-in MTP head(s) by default
(no separate GGUF). When a drafter model is set, llama.cpp loads that
GGUF as the MTP draft context instead (the has_draft branch of
common_speculative_init_result) — this is how models whose GGUF ships
no built-in MTP head (e.g. the lower quants of the newer Unsloth
Dynamic v3.0) still get MTP speculative decoding. The number of draft
tokens (--spec-draft-n-max) is clamped by llama.cpp to the number of
trained MTP heads.
"""

from __future__ import annotations

from ..schema import LaunchSettings
from .base import DRAFTER_OPTIONAL, Technique


class _MTP(Technique):
    def validate(self, s: LaunchSettings) -> list[str]:
        errors = super().validate(s)
        if s.mmproj.strip():
            errors.append(
                "mmproj (vision) and draft-mtp speculative decoding are incompatible — "
                "disable one of them"
            )
        return errors


TECHNIQUE = _MTP(
    spec_type="draft-mtp",
    label="draft-mtp (built-in or external MTP head)",
    description=(
        "Uses the model's own multi-token-prediction head; set a drafter model to "
        "use an external MTP GGUF instead (for targets that ship no built-in head). "
        "Incompatible with mmproj (vision)."
    ),
    drafter=DRAFTER_OPTIONAL,
)
