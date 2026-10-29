"""Set-based boundary observation -> the existing external-resolve feedback key.

The rich effect path (node-tar's `FilesystemEffectEvent` inside an `EffectEventTrace`)
exposes an ordered, entry-correlated completion boundary: every observed operation carries
start and completion ordinals, monotonic intervals, correlation ids and causal edges, and
`boundary_attempt_keys`/`external_resolve_keys` derive the M3.1 boundary-approach gradient
from it. A *second* extractor does not necessarily expose that structure. The decompress(JS)
entry-completion feasibility probe observed that decompress records entries concurrently and
reordered -- archive order is not call order, and it varies run to run -- and propagates no
entry context to the filesystem operation, so a faithful ordered `EffectEventTrace` cannot be
reconstructed from it. That is the same class of observation limit node-tar's own
entry-completion boundary hits (see `entry-transition-observation-v1.md`), and it means the
*ordered* transition gradient stays unrealized on this extractor family.

What such an adapter can still observe is a *set* of boundary-relevant operations: for each
one, which operation it was, where it wrote, the region its target resolved to, and whether
it aliased an external object -- with no reliable ordering, causality or operation outcome.
This module is the honest contract for that weaker observation. It deliberately does NOT
fabricate the ordered trace structure that was not observed (that would manufacture
evidence the probe says is not there); it carries only what was seen, and maps it into the
one M3.1 boundary-approach key that is itself purely region-based and needs none of the
fields a set observation lacks: `ExternalResolveSignature` (an observed operation whose
resolved path is EXTERNAL). The lexical `BoundaryAttemptSignature` is deliberately NOT a
target here: it requires the raw link text (for `escape_shape`) and the operation outcome,
neither of which a set observation carries.

Strictly additive and target-agnostic. It consumes no `EffectEventTrace`, changes no
existing derivation, and produces the same `OBSERVED_EXTERNAL_RESOLVE` key the trace path
produces, so the existing P3 consumption ranks keys from either extractor identically. It is
also answer-agnostic: the key reads only the operation kind and the EXTERNAL region, never a
concrete path, the declared-protected marker, a sentinel, a CVE or a PoC -- aliasing *some*
external object counts, never the protected one specifically (D005/D006). An external-resolve
key is boundary-approach evidence, never a C0/C1/C2 verdict and never a vulnerability.
"""

from dataclasses import dataclass
from typing import ClassVar

from inodefence.model import (
    EffectFeedbackKey,
    EffectFeedbackKeyKind,
    ExternalResolveSignature,
    ObservedOperationType,
    Region,
)


@dataclass(frozen=True, slots=True)
class ObservedBoundaryOperation:
    """One boundary-relevant filesystem operation an extractor adapter observed.

    The honest set-based unit for an extractor whose ordered entry-completion boundary is
    not observable. It is deliberately weaker than `FilesystemEffectEvent`: it carries no
    ordinal, interval, correlation id or causal edge, because those encode an ordering the
    adapter did not observe. The adapter surfaces only the operations it actually observed
    and classifies `target_region` through the generic `path_region`; it carries no oracle,
    CVE or target-specific path logic (architecture boundary).

    Fields:
    - `operation`: the observed filesystem operation (e.g. LINK for a hardlink, SYMLINK for
      a symlink). It is the signature's discriminator, so a hardlink and a symlink that both
      resolve external form distinct keys.
    - `entry_dest`: the archive entry's own destination path, for adapter-side traceability.
      It is intentionally NOT read by the answer-agnostic key (a concrete path would leak
      the specific object reached); see `external_resolve_keys_from_observations`.
    - `target_region`: the region the operation's target resolved to, from `path_region`.
      Only EXTERNAL yields a key.
    - `aliases_external`: whether the operation realized an identity alias to an external
      object (a hardlink) rather than merely referencing one (a dangling symlink). Carried
      for the adapter and the C1/C2 oracle; the answer-agnostic key does not rank by it.
    """

    serialization_schema: ClassVar[int] = 1

    operation: ObservedOperationType
    entry_dest: str
    target_region: Region
    aliases_external: bool

    def __post_init__(self) -> None:
        if not isinstance(self.operation, ObservedOperationType):
            raise ValueError("observed boundary operation requires an observed operation type")
        if not isinstance(self.entry_dest, str) or not self.entry_dest:
            raise ValueError("observed boundary operation requires a non-empty entry destination")
        if not isinstance(self.target_region, Region):
            raise ValueError("observed boundary operation requires a resolved target region")
        if type(self.aliases_external) is not bool:
            raise ValueError("observed boundary operation alias marker must be bool")


def _external_resolve_sort_key(key: EffectFeedbackKey) -> tuple[object, ...]:
    # Every key this module builds is an OBSERVED_EXTERNAL_RESOLVE over an
    # ExternalResolveSignature, so narrowing to it gives a total, deterministic order
    # without the union-wide ladder `feedback.effect._feedback_key_sort_key` needs.
    signature = key.signature
    assert isinstance(signature, ExternalResolveSignature)
    return signature.sort_key()


def external_resolve_keys_from_observations(
    observations: tuple[ObservedBoundaryOperation, ...],
) -> tuple[EffectFeedbackKey, ...]:
    """Map set-based boundary observations into `OBSERVED_EXTERNAL_RESOLVE` keys.

    Mirrors `feedback.effect.external_resolve_keys` but consumes the weaker set observation
    instead of an `EffectEventTrace`. An observation whose target resolved to the EXTERNAL
    region yields one `ExternalResolveSignature(operation, EXTERNAL)` key; any other region
    yields nothing. Duplicate observations collapse to one key (a set), and the result is in
    the same canonical order the trace path uses, so the two extractors' keys are drawn from
    one key space.

    Region-based and answer-agnostic: the key reads only the operation kind and the EXTERNAL
    region. It deliberately does NOT read `entry_dest` (a concrete path) or `aliases_external`
    -- a realized external identity alias and a dangling external reference both count as one
    external resolution, exactly as the trace-based derivation credits any external-resolved
    operation regardless of outcome. Ranking by which external object was reached, or by
    whether the alias was realized, would drift the reward toward the protected sentinel
    (D005/D006); whether a reached object is the protected sentinel, and whether an alias was
    realized, stay C1/C2 oracle judgments, never feedback. Like the trace-based keys this
    assumes nothing about termination; the caller gates on a clean, valid, complete run.
    """
    if not isinstance(observations, tuple) or not all(
        isinstance(observation, ObservedBoundaryOperation) for observation in observations
    ):
        raise ValueError(
            "external resolve observations must be a tuple of ObservedBoundaryOperation"
        )
    keys: set[EffectFeedbackKey] = set()
    for observation in observations:
        if observation.target_region != Region.EXTERNAL:
            continue
        keys.add(
            EffectFeedbackKey(
                EffectFeedbackKeyKind.OBSERVED_EXTERNAL_RESOLVE,
                ExternalResolveSignature(observation.operation, Region.EXTERNAL),
            )
        )
    return tuple(sorted(keys, key=_external_resolve_sort_key))
