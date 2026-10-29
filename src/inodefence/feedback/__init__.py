"""Normalized state, semantic violation novelty and in-memory search retention."""

from inodefence.model import EffectFeedbackKeyKind, TransitionBoundaryProximity

from .corpus import Corpus, CorpusEntry, CorpusStats, FeedbackDecision
from .coverage import StructureCoverageFeature, structure_coverage_features
from .effect import (
    boundary_attempt_keys,
    effect_feedback_eligible,
    effect_feedback_keys,
    external_resolve_keys,
    normalized_effect_signature,
)
from .effect_novelty import EffectNoveltyDecision, EffectNoveltyIndex
from .effect_search import (
    EffectCorpusEntry,
    EffectSearchDecision,
    EffectSearchPolicy,
    EffectSearchState,
    EffectSearchStats,
)
from .fingerprint import (
    ChangeFingerprint,
    IdentityFingerprint,
    ViolationFingerprint,
    violation_fingerprints,
)
from .projection import FeedbackKey, FeedbackProjection, feedback_key
from .rebinding import (
    derive_namespace_rebinding_sequences,
    effect_feedback_projection_v3,
    namespace_rebinding_signature,
)
from .search import SearchDecision, SearchPolicy, SearchState
from .signature import state_signature
from .transition import (
    transition_key,
    transition_keys,
    transition_sequence_key,
    transition_signature,
)
from .transition_gradient import (
    max_proximity,
    proximity_rank,
    trace_proximity,
    transition_proximities,
    transition_proximity,
)
from .transition_novelty import TransitionNoveltyDecision, TransitionNoveltyIndex
from .transition_search import (
    TransitionCorpusEntry,
    TransitionSearchDecision,
    TransitionSearchPolicy,
    TransitionSearchState,
    TransitionSearchStats,
)

__all__ = [
    "ChangeFingerprint",
    "Corpus",
    "CorpusEntry",
    "CorpusStats",
    "FeedbackDecision",
    "EffectCorpusEntry",
    "EffectFeedbackKeyKind",
    "EffectNoveltyDecision",
    "EffectNoveltyIndex",
    "EffectSearchDecision",
    "EffectSearchPolicy",
    "EffectSearchState",
    "EffectSearchStats",
    "boundary_attempt_keys",
    "external_resolve_keys",
    "effect_feedback_eligible",
    "effect_feedback_keys",
    "effect_feedback_projection_v3",
    "FeedbackKey",
    "FeedbackProjection",
    "feedback_key",
    "IdentityFingerprint",
    "normalized_effect_signature",
    "namespace_rebinding_signature",
    "SearchDecision",
    "SearchPolicy",
    "SearchState",
    "StructureCoverageFeature",
    "ViolationFingerprint",
    "state_signature",
    "structure_coverage_features",
    "transition_key",
    "transition_keys",
    "transition_sequence_key",
    "transition_signature",
    "transition_proximity",
    "transition_proximities",
    "trace_proximity",
    "proximity_rank",
    "max_proximity",
    "TransitionBoundaryProximity",
    "TransitionCorpusEntry",
    "TransitionNoveltyDecision",
    "TransitionNoveltyIndex",
    "TransitionSearchDecision",
    "TransitionSearchPolicy",
    "TransitionSearchState",
    "TransitionSearchStats",
    "violation_fingerprints",
    "derive_namespace_rebinding_sequences",
]
