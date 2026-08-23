"""MTP (multi-token prediction) speculative decoding — `draft-mtp`.

The drafter is the target model's own built-in MTP head(s); no separate
draft GGUF is loaded. The number of draft tokens (--spec-draft-n-max)
is clamped by llama.cpp to the number of trained MTP heads.
"""

from __future__ import annotations

from ..schema import LaunchSettings
from .base import Technique


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
    label="draft-mtp (built-in MTP head)",
    description=(
        "Uses the model's own multi-token-prediction head; no drafter file needed. "
        "Incompatible with mmproj (vision)."
    ),
    needs_drafter=False,
)
