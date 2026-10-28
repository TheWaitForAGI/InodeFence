"""Target-agnostic extraction-structure coverage key for baseline D.

Baseline D (coverage-guided) keeps the initial seed corpus as its base
population and admits a mutation parent when the extraction's observed structure
exercises a generic structural feature not yet seen in the campaign, in the
style of coverage-guided fuzzing (new feature -> keep input). The feature is
deliberately coarse and target-agnostic: object kind, namespace region
(extraction vs external), path depth and symlink-anchor class.

D deliberately never reads ``StateSignature.identity_groups`` (object-identity
relations) or ``StateSignature.external_effects`` (external sentinel effects) --
the two signals that encode InodeFence's own hypothesis. That exclusion is the
separation point from B1/B3: comparing a state-aware policy against D isolates
the specific contribution of identity/external-effect feedback from the general
contribution of any feedback-guided retention (H1; audit EN-008: new state count
is not effectiveness).

Scope and honest limits (observed/inferred): this is an output-structure coverage
PROXY, not instrumented code coverage of the extractor process, which the current
contained-execution boundary does not expose. It abstracts away content digests,
sizes, permission modes, raw inode/timestamp values and exact path names, so it
rewards new structural shape rather than new content. ``region`` is a fixed
runtime-layout fact (``path_region``), not an external-effect or identity label;
it lets D credibly cover the generic path-boundary dimension (which the project
positions as baseline, not novelty) while still excluding the identity/effect
labels. See docs/research/benchmarks/baseline-and-ablation-v1.md and
evaluation-protocol-v1.md for the comparison framing.
"""

from dataclasses import dataclass

from inodefence.model import ObjectType, Region, StateSignature
from inodefence.model.filesystem import path_region


@dataclass(frozen=True, slots=True)
class StructureCoverageFeature:
    """One generic structural coverage element of an extraction result.

    link_anchor is "run" or "literal" for a symlink (matching the tagged target
    prefix produced by state_signature), and None for every non-symlink object.
    No raw name, content, size, mode, inode or timestamp value is included.
    """

    object_type: ObjectType
    region: Region
    depth: int
    link_anchor: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.object_type, ObjectType) or not isinstance(self.region, Region):
            raise ValueError("coverage feature requires ObjectType and Region values")
        if type(self.depth) is not int or self.depth < 0:
            raise ValueError("coverage depth must be a nonnegative integer")
        if self.link_anchor not in (None, "run", "literal"):
            raise ValueError("link_anchor must be None, 'run' or 'literal'")
        if (self.object_type == ObjectType.SYMLINK) != (self.link_anchor is not None):
            raise ValueError("only symlink features carry a link anchor")


def _link_anchor(symlink_target: str | None) -> str | None:
    if symlink_target is None:
        return None
    return "run" if symlink_target.startswith("run:") else "literal"


def structure_coverage_features(signature: StateSignature) -> frozenset[StructureCoverageFeature]:
    """Project a normalized state signature onto its generic structural features.

    Pure function of signature.objects only; identity_groups and external_effects
    are never read. Depth is the number of path separators (top-level objects have
    depth 0). Determinism follows from StateSignature's sorted unique objects.
    """
    if not isinstance(signature, StateSignature):
        raise ValueError("structure coverage requires a StateSignature")
    return frozenset(
        StructureCoverageFeature(
            obj.object_type,
            path_region(obj.path),
            obj.path.count("/"),
            _link_anchor(obj.symlink_target),
        )
        for obj in signature.objects
    )
