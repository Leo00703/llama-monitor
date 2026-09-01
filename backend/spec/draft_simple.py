"""Classic draft model speculative decoding — `draft-simple`.

A much smaller draft model proposes tokens one at a time; the target
model verifies the whole draft in a single pass.
"""

from __future__ import annotations

from .base import DRAFTER_REQUIRED, Technique

TECHNIQUE = Technique(
    spec_type="draft-simple",
    label="draft-simple",
    description="Classic small draft model, one token at a time.",
    drafter=DRAFTER_REQUIRED,
)
