"""Behavioral parity between two execution methods' campaign evidence (G1).

This module never runs a target and never touches Docker. Given the typed
evidence two execution methods produced for the *same* ``(seed, arm, version)``
campaign -- the per-case fresh-container path (baseline) and the persistent
worker pool -- it decides whether they agree on the four G1 parity dimensions:

1. ``case_sequence`` -- the loop visited the same ``case_id`` values in the same
   order. Retries re-run the same case, so this is compared over every step.
2. ``oracle_and_feedback`` -- the C0/C1/C2 verdicts agree step by step, and the
   feedback keys the loop derived from each run agree. The feedback keys drive
   corpus admission and the adaptive scheduler, so equal oracle verdicts plus
   equal feedback keys are exactly "the loop saw the same security signal".
3. ``snapshots`` -- the BEFORE/AFTER object sets are identical once run-specific
   fields are excluded (``st_dev``, ``st_ino``, ``mtime_ns``, ``ctime_ns`` and
   the absolute ``sandbox_root``), and the inode-sharing partition (which paths
   share one ``(st_dev, st_ino)``) is identical. Raw inode numbers differ per
   run and per volume; their *sharing structure* is the identity semantics C1/C2
   depend on, so that is what parity compares.
4. ``isolation_and_reset`` -- the isolation provenance is identical and each
   method's per-case reset verification passed with the same verdict.

The headline (baseline) verdict compares two *retry-free* executions over their
clean steps. A step the worker pool had to retry (an infrastructure failure --
``BackendError`` or a reset-verification failure that recycled the worker) is
pulled out and given a *separate* verdict: did the post-retry result still match
the retry-free execution at that step? Retry records are opaque here; their
format is owned by the runtime abort classifier in another lane. This module
only reads how many retries a step carried, never why.
"""

from dataclasses import dataclass, fields
from enum import Enum

from inodefence.effect_campaign import EffectCampaignResult
from inodefence.model import canonical_json
from inodefence.model.filesystem import ObjectSnapshot, StateSnapshot
from inodefence.model.isolation import IsolationProvenance

# Raw per-run object fields that two correct executions are allowed to differ on.
# Identity numbers are excluded as raw values but retained as a sharing partition.
EXCLUDED_OBJECT_FIELDS: frozenset[str] = frozenset({"st_dev", "st_ino", "mtime_ns", "ctime_ns"})

# The object fields the parity tuple keeps, in declaration order: everything except
# the run-specific fields above. Deriving this from the dataclass makes
# EXCLUDED_OBJECT_FIELDS the single source of what is dropped, so adding a field to
# ObjectSnapshot shows up in the parity tuple unless it is explicitly excluded here.
_CANONICAL_OBJECT_FIELDS: tuple[str, ...] = tuple(
    field.name for field in fields(ObjectSnapshot) if field.name not in EXCLUDED_OBJECT_FIELDS
)

# Bound on how many per-item differences a dimension spells out, so a wildly
# divergent pair still produces a readable report instead of an unbounded dump.
_MAX_DETAIL = 20


@dataclass(frozen=True, slots=True)
class CanonicalSnapshot:
    """A StateSnapshot reduced to the fields two correct runs must share.

    ``sandbox_root`` (which embeds the per-case run UUID) is dropped. Each object
    keeps its structural fields; raw identity numbers and timestamps are dropped
    from the per-object tuple but preserved as ``identity_groups``.
    """

    phase: str
    protected_paths: tuple[str, ...]
    objects: tuple[tuple[object, ...], ...]
    identity_groups: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class ResetVerification:
    """One case's post-run sandbox reset result, in the runtime abort classifier's
    polarity (``True`` means that failure occurred).

    Field names mirror ``evaluation.abort_classification.ResetFailureDetail`` (owned
    by the runtime lane) so the worker pool maps its records 1:1 without re-spelling:
    ``reset_residual`` means a ``core-run-*`` directory survived the case, and
    ``reset_other_path_change`` means the volume's other top-level entries diverged
    from the worker's start-of-campaign baseline. A clean teardown has neither.
    """

    case_index: int
    reset_residual: bool
    reset_other_path_change: bool

    def __post_init__(self) -> None:
        if type(self.case_index) is not int or self.case_index < 0:
            raise ValueError("reset verification requires a nonnegative case index")
        if type(self.reset_residual) is not bool or type(self.reset_other_path_change) is not bool:
            raise ValueError("reset verification verdicts must be booleans")

    @property
    def passed(self) -> bool:
        return not self.reset_residual and not self.reset_other_path_change


@dataclass(frozen=True, slots=True)
class ParityStep:
    """One campaign step reduced to its parity-relevant evidence."""

    index: int
    case_id: str
    oracle: tuple[tuple[str, bool], ...]
    feedback_keys: tuple[str, ...]
    before: CanonicalSnapshot
    after: CanonicalSnapshot
    retry_count: int

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("parity step requires a nonnegative index")
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("parity step requires a nonempty case id")
        if type(self.retry_count) is not int or self.retry_count < 0:
            raise ValueError("parity step retry count must be a nonnegative integer")

    @property
    def retried(self) -> bool:
        return self.retry_count > 0


@dataclass(frozen=True, slots=True)
class ParitySubject:
    """One execution method's parity-relevant evidence for a single campaign."""

    label: str
    steps: tuple[ParityStep, ...]
    isolation: tuple[tuple[str, object], ...] | None
    resets: tuple[ResetVerification, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("parity subject requires a nonempty label")
        if not isinstance(self.steps, tuple) or not all(
            isinstance(step, ParityStep) for step in self.steps
        ):
            raise ValueError("parity subject requires ParityStep records")
        if tuple(step.index for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("parity subject step indexes must be contiguous from zero")
        if not isinstance(self.resets, tuple) or not all(
            isinstance(reset, ResetVerification) for reset in self.resets
        ):
            raise ValueError("parity subject resets must be ResetVerification records")

    @property
    def retry_free(self) -> bool:
        return all(not step.retried for step in self.steps)


def canonical_object(obj: ObjectSnapshot) -> tuple[object, ...]:
    """A single object's parity tuple: structural fields, no raw identity or time.

    Built from ``_CANONICAL_OBJECT_FIELDS`` (every ObjectSnapshot field except
    ``EXCLUDED_OBJECT_FIELDS``). Enum values are reduced to their stable string so
    the tuple is comparable and JSON-able.
    """
    values: list[object] = []
    for name in _CANONICAL_OBJECT_FIELDS:
        value = getattr(obj, name)
        values.append(value.value if isinstance(value, Enum) else value)
    return tuple(values)


def canonical_snapshot(snapshot: StateSnapshot) -> CanonicalSnapshot:
    """Reduce a StateSnapshot to its cross-run-stable parity form."""
    return CanonicalSnapshot(
        phase=snapshot.phase.value,
        protected_paths=tuple(snapshot.protected_paths),
        objects=tuple(canonical_object(obj) for obj in snapshot.objects),
        identity_groups=snapshot.identity_groups(),
    )


def normalize_isolation(provenance: IsolationProvenance) -> tuple[tuple[str, object], ...]:
    """Sorted isolation facts two workers must share (image, runtime, policy).

    IsolationProvenance carries no volume name, container id or timestamp, so no
    field is dropped here; the whole record is a parity invariant. The policy's
    image id is the local content-addressed image, identical across workers that
    were pre-started from the same digest.
    """
    policy = provenance.policy
    return tuple(
        sorted(
            {
                "image_id": policy.image_id,
                "uid": policy.uid,
                "gid": policy.gid,
                "implementation_id": policy.implementation_id,
                "filesystem_view": policy.filesystem_view,
                "network_policy": policy.network_policy,
                "rootfs_mode": policy.rootfs_mode,
                "cap_drop": tuple(policy.cap_drop),
                "no_new_privileges": policy.no_new_privileges,
                "pid_namespace": policy.pid_namespace,
                "ipc_namespace": policy.ipc_namespace,
                "cgroup_namespace": policy.cgroup_namespace,
                "environment_policy": policy.environment_policy,
                "runtime_name": provenance.runtime_name,
                "runtime_version": provenance.runtime_version,
                "runtime_api_version": provenance.runtime_api_version,
                "runtime_os": provenance.runtime_os,
                "runtime_architecture": provenance.runtime_architecture,
                "image_architecture": provenance.image_architecture,
                "image_repo_digests": tuple(provenance.image_repo_digests),
            }.items()
        )
    )


def extract_parity_subject(
    result: EffectCampaignResult,
    *,
    label: str,
    isolation: IsolationProvenance | None = None,
    resets: tuple[ResetVerification, ...] = (),
    retries: dict[int, int] | None = None,
) -> ParitySubject:
    """Build a ParitySubject from one method's typed campaign evidence.

    ``retries`` maps a step index to how many infra retries that step needed
    (default zero). ``resets`` are the per-case reset verdicts the method
    recorded. ``isolation`` is the campaign's captured isolation provenance.
    """
    if not isinstance(result, EffectCampaignResult):
        raise ValueError("parity extraction requires an EffectCampaignResult")
    retry_counts = dict(retries or {})
    steps = tuple(
        ParityStep(
            index=step.index,
            case_id=step.result.base_result.case.case_id,
            oracle=tuple(
                sorted(
                    (verdict.contract_id.value, verdict.violated)
                    for verdict in step.result.base_result.violations
                )
            ),
            feedback_keys=_feedback_keys(step),
            before=canonical_snapshot(step.result.base_result.before),
            after=canonical_snapshot(step.result.base_result.after),
            retry_count=retry_counts.get(step.index, 0),
        )
        for step in result.steps
    )
    return ParitySubject(
        label=label,
        steps=steps,
        isolation=None if isolation is None else normalize_isolation(isolation),
        resets=tuple(resets),
    )


def _feedback_keys(step: object) -> tuple[str, ...]:
    """Canonical, order-stable encoding of the feedback a step fed back to the loop."""
    feedback = step.feedback  # type: ignore[attr-defined]
    keys = [canonical_json(key) for key in feedback.new_effect_keys]
    keys += [canonical_json(item) for item in feedback.new_violation_fingerprints]
    return tuple(keys)


@dataclass(frozen=True, slots=True)
class DimensionResult:
    """One parity dimension's verdict over the compared steps."""

    name: str
    agree: bool
    detail: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetriedStepVerdict:
    """A step at least one method retried, judged against the retry-free run."""

    index: int
    case_id: str
    baseline_retries: int
    candidate_retries: int
    matches_retry_free: bool
    detail: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParityReport:
    """The full parity decision for one baseline/candidate pair."""

    baseline_label: str
    candidate_label: str
    both_retry_free: bool
    dimensions: tuple[DimensionResult, ...]
    retried_steps: tuple[RetriedStepVerdict, ...]

    @property
    def core_parity(self) -> bool:
        """Do the four dimensions agree over the clean (non-retried) steps?"""
        return all(dimension.agree for dimension in self.dimensions)

    @property
    def passed(self) -> bool:
        """Headline parity holds and every retried step stayed transparent."""
        return self.core_parity and all(
            verdict.matches_retry_free for verdict in self.retried_steps
        )


def compare_subjects(baseline: ParitySubject, candidate: ParitySubject) -> ParityReport:
    """Compare two methods' evidence across the four G1 parity dimensions.

    The four dimensions form the headline verdict over steps neither method
    retried. ``case_sequence`` is judged over every step because a retry re-runs
    the same case. Steps either method retried get a separate per-step verdict.
    """
    if not isinstance(baseline, ParitySubject) or not isinstance(candidate, ParitySubject):
        raise ValueError("parity comparison requires two ParitySubject records")

    clean = _clean_indices(baseline, candidate)
    dimensions = (
        _dimension_case_sequence(baseline, candidate),
        _dimension_oracle_and_feedback(baseline, candidate, clean),
        _dimension_snapshots(baseline, candidate, clean),
        _dimension_isolation_and_reset(baseline, candidate, clean),
    )
    retried = _retried_step_verdicts(baseline, candidate)
    return ParityReport(
        baseline_label=baseline.label,
        candidate_label=candidate.label,
        both_retry_free=baseline.retry_free and candidate.retry_free,
        dimensions=dimensions,
        retried_steps=retried,
    )


def _aligned_indices(baseline: ParitySubject, candidate: ParitySubject) -> range:
    return range(min(len(baseline.steps), len(candidate.steps)))


def _clean_indices(baseline: ParitySubject, candidate: ParitySubject) -> tuple[int, ...]:
    return tuple(
        index
        for index in _aligned_indices(baseline, candidate)
        if not baseline.steps[index].retried and not candidate.steps[index].retried
    )


def _bounded(detail: list[str]) -> tuple[str, ...]:
    if len(detail) <= _MAX_DETAIL:
        return tuple(detail)
    return (*detail[:_MAX_DETAIL], f"... {len(detail) - _MAX_DETAIL} more difference(s)")


def _dimension_case_sequence(baseline: ParitySubject, candidate: ParitySubject) -> DimensionResult:
    detail: list[str] = []
    if len(baseline.steps) != len(candidate.steps):
        detail.append(f"step count differs: {len(baseline.steps)} vs {len(candidate.steps)}")
    for index in _aligned_indices(baseline, candidate):
        left = baseline.steps[index].case_id
        right = candidate.steps[index].case_id
        if left != right:
            detail.append(f"step {index}: case id {left} vs {right}")
    return DimensionResult("case_sequence", not detail, _bounded(detail))


def _dimension_oracle_and_feedback(
    baseline: ParitySubject, candidate: ParitySubject, clean: tuple[int, ...]
) -> DimensionResult:
    detail: list[str] = []
    for index in clean:
        left = baseline.steps[index]
        right = candidate.steps[index]
        if left.oracle != right.oracle:
            detail.append(f"step {index}: oracle {left.oracle} vs {right.oracle}")
        if left.feedback_keys != right.feedback_keys:
            detail.append(
                f"step {index}: feedback keys differ "
                f"({len(left.feedback_keys)} vs {len(right.feedback_keys)})"
            )
    return DimensionResult("oracle_and_feedback", not detail, _bounded(detail))


def _snapshot_detail(
    index: int, phase: str, a: CanonicalSnapshot, b: CanonicalSnapshot
) -> list[str]:
    detail: list[str] = []
    if a.protected_paths != b.protected_paths:
        detail.append(f"step {index} {phase}: protected paths differ")
    if a.objects != b.objects:
        left = {str(obj[0]) for obj in a.objects}
        right = {str(obj[0]) for obj in b.objects}
        only_left = sorted(left - right)
        only_right = sorted(right - left)
        if only_left:
            detail.append(f"step {index} {phase}: only baseline has {only_left}")
        if only_right:
            detail.append(f"step {index} {phase}: only candidate has {only_right}")
        for obj_a, obj_b in zip(a.objects, b.objects, strict=False):
            if obj_a[0] == obj_b[0] and obj_a != obj_b:
                detail.append(f"step {index} {phase}: object {obj_a[0]!r} fields differ")
    if a.identity_groups != b.identity_groups:
        detail.append(
            f"step {index} {phase}: inode-sharing partition "
            f"{a.identity_groups} vs {b.identity_groups}"
        )
    return detail


def _dimension_snapshots(
    baseline: ParitySubject, candidate: ParitySubject, clean: tuple[int, ...]
) -> DimensionResult:
    detail: list[str] = []
    for index in clean:
        left = baseline.steps[index]
        right = candidate.steps[index]
        detail += _snapshot_detail(index, "before", left.before, right.before)
        detail += _snapshot_detail(index, "after", left.after, right.after)
    return DimensionResult("snapshots", not detail, _bounded(detail))


def _dimension_isolation_and_reset(
    baseline: ParitySubject, candidate: ParitySubject, clean: tuple[int, ...]
) -> DimensionResult:
    detail: list[str] = []
    if baseline.isolation is None or candidate.isolation is None:
        detail.append("isolation provenance not provided by both methods")
    elif baseline.isolation != candidate.isolation:
        left = dict(baseline.isolation)
        right = dict(candidate.isolation)
        for key in sorted(set(left) | set(right)):
            if left.get(key) != right.get(key):
                detail.append(f"isolation {key}: {left.get(key)!r} vs {right.get(key)!r}")

    baseline_resets = {reset.case_index: reset for reset in baseline.resets}
    candidate_resets = {reset.case_index: reset for reset in candidate.resets}
    for index in clean:
        left = baseline_resets.get(index)
        right = candidate_resets.get(index)
        if left is None or right is None:
            detail.append(f"step {index}: reset verification missing from a method")
            continue
        if not left.passed or not right.passed:
            left_flags = (left.reset_residual, left.reset_other_path_change)
            right_flags = (right.reset_residual, right.reset_other_path_change)
            detail.append(
                f"step {index}: reset not clean "
                f"(baseline residual/other={left_flags}; candidate residual/other={right_flags})"
            )
        elif (left.reset_residual, left.reset_other_path_change) != (
            right.reset_residual,
            right.reset_other_path_change,
        ):
            detail.append(f"step {index}: reset verdict differs")
    return DimensionResult("isolation_and_reset", not detail, _bounded(detail))


def _retried_step_verdicts(
    baseline: ParitySubject, candidate: ParitySubject
) -> tuple[RetriedStepVerdict, ...]:
    verdicts: list[RetriedStepVerdict] = []
    for index in _aligned_indices(baseline, candidate):
        left = baseline.steps[index]
        right = candidate.steps[index]
        if not left.retried and not right.retried:
            continue
        detail: list[str] = []
        if left.case_id != right.case_id:
            detail.append(f"case id {left.case_id} vs {right.case_id}")
        if left.oracle != right.oracle:
            detail.append(f"oracle {left.oracle} vs {right.oracle}")
        if left.feedback_keys != right.feedback_keys:
            detail.append("feedback keys differ")
        detail += _snapshot_detail(index, "before", left.before, right.before)
        detail += _snapshot_detail(index, "after", left.after, right.after)
        verdicts.append(
            RetriedStepVerdict(
                index=index,
                case_id=right.case_id,
                baseline_retries=left.retry_count,
                candidate_retries=right.retry_count,
                matches_retry_free=not detail,
                detail=_bounded(detail),
            )
        )
    return tuple(verdicts)


# ---------------------------------------------------------------------------
# JSON round-trip for a ParitySubject. The worker-pool run extracts a subject
# inside the controller (where the typed EffectCampaignResult lives), writes it
# as JSON, and the host reads both methods' subjects back to compare them. The
# round-trip restores tuples so a deserialized subject equals a freshly extracted
# one (lists in JSON -> tuples here).
# ---------------------------------------------------------------------------


def _isolation_value_to_json(value: object) -> object:
    return list(value) if isinstance(value, tuple) else value


def _isolation_value_from_json(value: object) -> object:
    return tuple(value) if isinstance(value, list) else value


def _snapshot_to_dict(snapshot: CanonicalSnapshot) -> dict[str, object]:
    return {
        "phase": snapshot.phase,
        "protected_paths": list(snapshot.protected_paths),
        "objects": [list(obj) for obj in snapshot.objects],
        "identity_groups": [list(group) for group in snapshot.identity_groups],
    }


def _snapshot_from_dict(value: dict) -> CanonicalSnapshot:
    return CanonicalSnapshot(
        phase=value["phase"],
        protected_paths=tuple(value["protected_paths"]),
        objects=tuple(tuple(obj) for obj in value["objects"]),
        identity_groups=tuple(tuple(group) for group in value["identity_groups"]),
    )


def _step_to_dict(step: ParityStep) -> dict[str, object]:
    return {
        "index": step.index,
        "case_id": step.case_id,
        "oracle": [list(verdict) for verdict in step.oracle],
        "feedback_keys": list(step.feedback_keys),
        "before": _snapshot_to_dict(step.before),
        "after": _snapshot_to_dict(step.after),
        "retry_count": step.retry_count,
    }


def _step_from_dict(value: dict) -> ParityStep:
    return ParityStep(
        index=value["index"],
        case_id=value["case_id"],
        oracle=tuple((str(v[0]), bool(v[1])) for v in value["oracle"]),
        feedback_keys=tuple(value["feedback_keys"]),
        before=_snapshot_from_dict(value["before"]),
        after=_snapshot_from_dict(value["after"]),
        retry_count=value["retry_count"],
    )


def _reset_to_dict(reset: ResetVerification) -> dict[str, object]:
    return {
        "case_index": reset.case_index,
        "reset_residual": reset.reset_residual,
        "reset_other_path_change": reset.reset_other_path_change,
    }


def _reset_from_dict(value: dict) -> ResetVerification:
    return ResetVerification(
        value["case_index"], value["reset_residual"], value["reset_other_path_change"]
    )


def parity_subject_to_dict(subject: ParitySubject) -> dict[str, object]:
    """A JSON-able mapping of a ParitySubject (schema-tagged)."""
    return {
        "schema": "parity-subject-v1",
        "label": subject.label,
        "steps": [_step_to_dict(step) for step in subject.steps],
        "isolation": None
        if subject.isolation is None
        else [[key, _isolation_value_to_json(value)] for key, value in subject.isolation],
        "resets": [_reset_to_dict(reset) for reset in subject.resets],
    }


def parity_subject_from_dict(value: dict) -> ParitySubject:
    """Rebuild a ParitySubject from :func:`parity_subject_to_dict` output."""
    isolation = (
        None
        if value["isolation"] is None
        else tuple((pair[0], _isolation_value_from_json(pair[1])) for pair in value["isolation"])
    )
    return ParitySubject(
        label=value["label"],
        steps=tuple(_step_from_dict(step) for step in value["steps"]),
        isolation=isolation,
        resets=tuple(_reset_from_dict(reset) for reset in value["resets"]),
    )
