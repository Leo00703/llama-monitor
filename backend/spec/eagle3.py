"""EAGLE-3 speculative decoding — `draft-eagle3`.

A one-layer draft model reads the target model's hidden states to
propose tokens, reaching higher acceptance than a standalone draft of
the same size. Shares the target's tokenizer.
"""

from __future__ import annotations

from .base import DRAFTER_REQUIRED, Technique

TECHNIQUE = Technique(
    spec_type="draft-eagle3",
    label="draft-eagle3",
    description="One-layer draft reading the target's hidden states; higher acceptance than a standalone draft.",
    drafter=DRAFTER_REQUIRED,
)
