"""In-memory search retention using independent state and violation novelty."""

import random
from dataclasses import dataclass

from inodefence.model import ArchiveCase, RunResult, StateSignature

from .fingerprint import ViolationFingerprint, violation_fingerprints


@dataclass(frozen=True, slots=True)
class FeedbackDecision:
    """Explain one observation's novelty separately from new-case admission.

    A novel normalized state or contract-evidence class is interesting for
    search. This makes no safety claim. A retained case can produce an
    interesting observation without adding another copy of the case.
    """

    case_id: str
    state_novel: bool
    new_violation_fingerprints: tuple[ViolationFingerprint, ...]
    already_retained: bool

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("case ID must be nonempty text")
        if type(self.state_novel) is not bool or type(self.already_retained) is not bool:
            raise ValueError("feedback flags must be bools")
        _validate_fingerprints(self.new_violation_fingerprints)

    @property
    def interesting(self) -> bool:
        return self.state_novel or bool(self.new_violation_fingerprints)

    @property
    def retained(self) -> bool:
        """Whether this observation admitted a new mutation parent."""
        return self.interesting and not self.already_retained


@dataclass(frozen=True, slots=True)
class CorpusEntry:
    """Mutation parent and compact metadata from its first admission.

    Preserve the admitting signature and all semantic violation fingerprints,
    including any previously seen classes. Later observations never overwrite
    admission metadata. Full RunResult evidence belongs to the campaign caller.
    """

    case: ArchiveCase
    admission_signature: StateSignature
    admission_violation_fingerprints: tuple[ViolationFingerprint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case, ArchiveCase) or not isinstance(
            self.admission_signature, StateSignature
        ):
            raise ValueError("corpus entry requires ArchiveCase and StateSignature records")
        _validate_fingerprints(self.admission_violation_fingerprints)


def _validate_fingerprints(fingerprints: tuple[ViolationFingerprint, ...]) -> None:
    if not isinstance(fingerprints, tuple) or not all(
        isinstance(fingerprint, ViolationFingerprint) for fingerprint in fingerprints
    ):
        raise ValueError("fingerprints must be a tuple of ViolationFingerprint records")


@dataclass(frozen=True, slots=True)
class CorpusStats:
    """Trusted Corpus-produced counters; these are not imported evidence.

    Arbitrary direct construction does not validate counter arithmetic.
    """

    observations: int
    interesting_observations: int
    retained_cases: int
    unique_states: int
    unique_violation_fingerprints: int


class Corpus:
    """Evolving search state for one caller-controlled campaign context.

    StateSignature equality and semantic violation fingerprints are independent
    novelty channels. Same-signature observations may expose new C0 evidence in
    HARNESS, which normalization deliberately excludes. Case identity only
    prevents duplicate parents; case/TAR identity and process evidence do not
    create novelty. Retention preserves future mutation parents, not findings.

    The caller owns target/configuration, seed, budgets and environment
    provenance. RunResult cannot identify a complete campaign context; do not
    mix contexts or assume cross-target comparison/persistence safety. This
    object performs no execution, mutation, filesystem IO or persistence.
    """

    def __init__(self) -> None:
        self._entries: list[CorpusEntry] = []
        self._retained_case_ids: set[str] = set()
        self._seen_states: set[StateSignature] = set()
        self._seen_violations: set[ViolationFingerprint] = set()
        self._observations = 0
        self._interesting_observations = 0

    def consider(self, result: RunResult) -> FeedbackDecision:
        """Observe both novelty channels, then admit an interesting unique case.

        Seen indexes advance even when a case was already retained. No full
        RunResult is stored. Decisions describe this observation; entries retain
        the original admission metadata. Execution outcome/duration is unused.
        """
        case_id = result.case.case_id
        fingerprints = violation_fingerprints(result.violations)
        decision = FeedbackDecision(
            case_id=case_id,
            state_novel=result.signature not in self._seen_states,
            new_violation_fingerprints=tuple(
                fingerprint
                for fingerprint in fingerprints
                if fingerprint not in self._seen_violations
            ),
            already_retained=case_id in self._retained_case_ids,
        )
        self._seen_states.add(result.signature)
        self._seen_violations.update(fingerprints)
        self._observations += 1
        if decision.interesting:
            self._interesting_observations += 1
        if decision.retained:
            self._entries.append(CorpusEntry(result.case, result.signature, fingerprints))
            self._retained_case_ids.add(case_id)
        return decision

    def select_case(self, rng: random.Random) -> ArchiveCase:
        """Uniform baseline selection using only caller RNG and insertion order.

        Same insertion order and RNG state give the same selection. No adaptive
        scheduling, implicit seeding or mutation occurs. Empty selection raises
        ValueError without consuming RNG state.
        """
        if not self._entries:
            raise ValueError("cannot select a case from an empty corpus")
        return rng.choice(self._entries).case

    @property
    def entries(self) -> tuple[CorpusEntry, ...]:
        """Immutable snapshot of retained entries in admission order."""
        return tuple(self._entries)

    @property
    def stats(self) -> CorpusStats:
        return CorpusStats(
            observations=self._observations,
            interesting_observations=self._interesting_observations,
            retained_cases=len(self._entries),
            unique_states=len(self._seen_states),
            unique_violation_fingerprints=len(self._seen_violations),
        )

    def __len__(self) -> int:
        return len(self._entries)
