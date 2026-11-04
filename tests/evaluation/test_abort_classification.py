"""Unit tests for the shared invalid-reason vocabulary and abort classifier.

The reason strings asserted here are the harness-generated messages produced by
``execution/docker_client.py`` and ``execution/container.py``, confirmed against
retained raw evidence (``~/inodefence-evidence``): broker-disconnect, cleanup
inspect, cleanup remove / removal-not-verified, and evidence-integrity. They are
embedded so the check is reproducible in CI without host evidence.
"""

import pytest

from inodefence.evaluation.abort_classification import (
    INFRASTRUCTURE_REASONS,
    MAX_INFRA_RETRIES,
    RETRY_BACKOFF_BASE_SECONDS,
    RETRY_BACKOFF_CAP_SECONDS,
    InvalidReason,
    ResetFailureDetail,
    classify_abort_reason,
    is_infrastructure_abort,
)

# Wrapped form the producer emits: "<module>.<qualname>: <message>".
_WRAP = "inodefence.execution.base.BackendError: "


@pytest.mark.parametrize(
    "reason, expected",
    [
        # broker
        ("trusted Docker broker disconnected or returned invalid data", InvalidReason.BROKER),
        (
            _WRAP + "trusted Docker broker disconnected or returned invalid data",
            InvalidReason.BROKER,
        ),
        # cleanup_inspect (the real string carries a trailing ": <stderr>")
        ("container runtime cleanup inspect failed: ", InvalidReason.CLEANUP_INSPECT),
        (
            _WRAP + "container runtime cleanup inspect failed: Error response from daemon: x",
            InvalidReason.CLEANUP_INSPECT,
        ),
        # cleanup_remove family
        ("container runtime remove failed: conflict", InvalidReason.CLEANUP_REMOVE),
        ("container removal could not be verified", InvalidReason.CLEANUP_REMOVE),
        (
            "refusing to remove a container owned by another invocation",
            InvalidReason.CLEANUP_REMOVE,
        ),
        # observer_integrity (pre-existing fail-closed class; not retried)
        (
            "evidence integrity failed after target success: {'integrity_valid': False}",
            InvalidReason.OBSERVER_INTEGRITY,
        ),
        ("evidence integrity failed(malformed_identity)", InvalidReason.OBSERVER_INTEGRITY),
        # state-observer ObservationError (wrapped form): observer-side, not infra
        (
            "inodefence.observer.snapshot.ObservationError: cannot observe outside/x",
            InvalidReason.OBSERVER_INTEGRITY,
        ),
        # other (named by code but not an infra-recoverable class)
        ("image node-tar 7.5.2 differs from repository pin 7.5.22", InvalidReason.OTHER),
        ("node-tar execution identity changed after setup", InvalidReason.OTHER),
        ("container target could not start", InvalidReason.OTHER),
        ("created container differs from required execution policy: ...", InvalidReason.OTHER),
        ("forced abort in test", InvalidReason.OTHER),
        ("", InvalidReason.OTHER),
    ],
)
def test_classify_abort_reason(reason: str, expected: InvalidReason) -> None:
    assert classify_abort_reason(reason) == expected


def test_shared_vocabulary_is_the_agreed_set() -> None:
    assert {reason.value for reason in InvalidReason} == {
        "observer_integrity",
        "broker",
        "cleanup_inspect",
        "cleanup_remove",
        "cleanup_reset",
        "other",
    }


def test_reset_failure_detail_values() -> None:
    assert {detail.value for detail in ResetFailureDetail} == {
        "reset_residual",
        "reset_other_path_change",
    }


def test_classifier_never_returns_cleanup_reset() -> None:
    # cleanup_reset is detected by reset verification, not from an abort string.
    strings = [
        "trusted Docker broker disconnected",
        "container runtime cleanup inspect failed: x",
        "container runtime remove failed: x",
        "evidence integrity failed after target success: {}",
        "anything else",
        "",
    ]
    assert all(classify_abort_reason(s) != InvalidReason.CLEANUP_RESET for s in strings)


def test_infrastructure_reasons_exclude_observer_and_other() -> None:
    assert INFRASTRUCTURE_REASONS == frozenset(
        {
            InvalidReason.BROKER,
            InvalidReason.CLEANUP_INSPECT,
            InvalidReason.CLEANUP_REMOVE,
            InvalidReason.CLEANUP_RESET,
        }
    )
    assert InvalidReason.OBSERVER_INTEGRITY not in INFRASTRUCTURE_REASONS
    assert InvalidReason.OTHER not in INFRASTRUCTURE_REASONS


def test_is_infrastructure_abort() -> None:
    assert is_infrastructure_abort("trusted Docker broker disconnected or returned invalid data")
    assert is_infrastructure_abort("container runtime cleanup inspect failed: x")
    assert is_infrastructure_abort("container runtime remove failed: x")
    # observer_integrity is explicitly NOT an infrastructure (retry-eligible) abort.
    assert not is_infrastructure_abort("evidence integrity failed after target success: {}")
    assert not is_infrastructure_abort("node-tar execution identity changed after setup")
    # state-observer ObservationError is observer-side, never retried.
    assert not is_infrastructure_abort(
        "inodefence.observer.snapshot.ObservationError: cannot open sandbox: x"
    )
    assert not is_infrastructure_abort("")


def test_reason_must_be_a_string() -> None:
    with pytest.raises(TypeError):
        classify_abort_reason(None)  # type: ignore[arg-type]


def test_first_match_wins_broker_before_cleanup() -> None:
    reason = "trusted Docker broker disconnected; container runtime remove failed"
    assert classify_abort_reason(reason) == InvalidReason.BROKER


def test_retry_policy_constants_are_sane() -> None:
    assert MAX_INFRA_RETRIES == 2
    assert 0 < RETRY_BACKOFF_BASE_SECONDS <= RETRY_BACKOFF_CAP_SECONDS
