"""Speculative decoding techniques (issue #17) — one module per technique.

The registry maps the --spec-type values implemented by llama.cpp main
to Technique objects (UI metadata, extra fields, flag translation,
validation). The ngram-* family stays selectable via the raw type field
(schema.SPEC_TYPES superset) but has no registry entry — it needs no
drafter or extra fields.
"""

from __future__ import annotations

from typing import Optional

from .base import Technique
from .dflash import TECHNIQUE as _DFLASH
from .dspark import TECHNIQUE as _DSPARK
from .draft_simple import TECHNIQUE as _DRAFT_SIMPLE
from .eagle3 import TECHNIQUE as _EAGLE3
from .mtp import TECHNIQUE as _MTP

TECHNIQUES: dict[str, Technique] = {
    t.spec_type: t
    for t in (_MTP, _DFLASH, _DSPARK, _DRAFT_SIMPLE, _EAGLE3)
}


def get(spec_type: str) -> Optional[Technique]:
    """The technique for a --spec-type value, or None (none/ngram-*/unknown)."""
    return TECHNIQUES.get(spec_type)


__all__ = ["Technique", "TECHNIQUES", "get"]
