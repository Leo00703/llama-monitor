"""MTP (multi-token prediction) speculative decoding — `draft-mtp`.

The drafter is the target model's own built-in MTP head(s) by default
(no separate GGUF). When a drafter model is set, llama.cpp loads that
GGUF as the MTP draft context instead (the has_draft branch of
common_speculative_init_result) — this is how models whose GGUF ships
no built-in MTP head (e.g. the lower quants of the newer Unsloth
Dynamic v3.0) still get MTP speculative decoding. The number of draft
tokens (--spec-draft-n-max) is clamped by llama.cpp to the number of
trained MTP heads.

Vision (mmproj) is compatible: the MTP draft hook skips embedding
(vision) batches, so image prefill passes through untouched
(common/speculative.cpp process()).
"""

from __future__ import annotations

from .base import DRAFTER_OPTIONAL, Technique

TECHNIQUE = Technique(
    spec_type="draft-mtp",
    label="draft-mtp (built-in or external MTP head)",
    description=(
        "Uses the model's own multi-token-prediction head; set a drafter model to "
        "use an external MTP GGUF instead (for targets that ship no built-in head). "
        "Compatible with mmproj (vision)."
    ),
    drafter=DRAFTER_OPTIONAL,
)
