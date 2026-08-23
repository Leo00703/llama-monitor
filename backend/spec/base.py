"""Base type for speculative decoding techniques (issue #17).

One module per technique in llama.cpp main. A Technique knows its
--spec-type id, its UI metadata, which extra preset fields it needs,
and how to translate SpecSettings into CLI tokens. Shared behaviour
(drafter model, n-max/n-min) lives here; modules only add what is
specific to their technique.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..schema import LaunchSettings, SpecSettings

# resolves a model-relative path to an absolute one (FlagContext.resolve)
Resolver = Callable[[str], str]


@dataclass
class Technique:
    spec_type: str
    label: str
    description: str
    needs_drafter: bool = False
    extra_fields: tuple[str, ...] = field(default_factory=tuple)

    def flags(self, spec: SpecSettings, resolve: Resolver) -> list[str]:
        """CLI tokens for this technique (excluding --spec-type itself)."""
        out: list[str] = []
        if self.needs_drafter and spec.draft_model.strip():
            out.extend(["--spec-draft-model", resolve(spec.draft_model)])
        if spec.draft_n_max > 0:
            out.extend(["--spec-draft-n-max", str(spec.draft_n_max)])
        if spec.draft_n_min > 0:
            out.extend(["--spec-draft-n-min", str(spec.draft_n_min)])
        return out

    def validate(self, s: LaunchSettings) -> list[str]:
        errors: list[str] = []
        if self.needs_drafter and not s.spec.draft_model.strip():
            errors.append(
                f"speculative decoding type '{self.spec_type}' requires a drafter model "
                "(spec.draft_model)"
            )
        return errors
