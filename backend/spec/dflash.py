"""DFlash speculative decoding — `draft-dflash`.

Block-diffusion draft: the draft model emits a whole block of tokens in
a single forward pass, injecting the target's hidden states into its
attention. --spec-draft-n-max is clamped by llama.cpp to the draft
model's trained block size.
"""

from __future__ import annotations

from .base import DRAFTER_REQUIRED, Technique

TECHNIQUE = Technique(
    spec_type="draft-dflash",
    label="draft-dflash",
    description="Block-diffusion draft; emits a whole token block per forward pass. n-max is clamped to the draft's trained block size.",
    drafter=DRAFTER_REQUIRED,
)
